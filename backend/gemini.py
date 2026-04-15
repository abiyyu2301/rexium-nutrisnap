"""
backend/gemini.py -- Vertex AI Gemini 1.5 Flash Vision Integration

Two-step approach:
  Step 1: Gemini 1.5 Flash identifies foods and estimates portions from image
  Step 2: main.py matches food names against the Firestore nutrition DB

Authentication via:
  - Service account (Cloud Run / VM): google.auth.default() → google.genai Client(vertexai=True)
  - Local dev: GEMINI_API_KEY env var (direct Gemini API)
"""
import base64
import json
import os
import re
from io import BytesIO
from typing import Optional

import google.auth
from PIL import Image

# ── google.genai Client (new SDK -- not the deprecated google-cloud-aiplatform) ──

GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GCP_PROJECT_ID", ""))
GCP_LOCATION = os.getenv("GCP_LOCATION", "asia-southeast1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))


# ── System + User Prompts ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are NutriSnap, an expert food identification and nutrition estimation AI.
Your task is to analyze meal photos and identify all distinct food and drink items present.

CRITICAL -- ONE PLATE, NOT MULTIPLE PLATES:
- All items you list belong to ONE single plate/meal/hand.
- Do NOT list the same dish split into parts (e.g., do NOT list "hainanese chicken rice" AND "fragrant rice" AND "roasted chicken" separately -- these are the SAME dish. List it as ONE entry: "hainanese chicken rice" with ONE combined portion).
- The sum of ALL portion_grams_estimate values must be realistic for a single meal: 200g--500g depending on plate size. If your individual portions sum to more than 500g, you are double-counting -- consolidate.
- A standard dinner plate (one person) = 250-350g total. A big plate = 350-500g.

For each item, estimate the portion size using visual cues
(plate size, compare to fist/hand, typical serving conventions).

OUTPUT FORMAT -- respond ONLY with valid JSON in this exact structure:
{
  "foods": [
    {
      "name": "specific food name in English or Indonesian",
      "description": "brief description of the item and how you identified it",
      "portion_description": "your estimated portion (e.g. '1 small plate ~150g', '2 tablespoons', '1 glass 240ml')",
      "portion_grams_estimate": number in grams,
      "confidence": number between 0.0 and 1.0
    }
  ],
  "total_grams_estimate": number in grams -- must be realistic for ONE plate (250-500g max),
  "overall_confidence": number between 0.0 and 1.0,
  "notes": "any observations about image quality, lighting, or ambiguity"
}

PORTION ESTIMATION GUIDELINES:
- A fist = ~150g (use as reference for rice on a plate -- NOT 200g, most rice portions are smaller than a fist)
- A tablespoon = ~15g (for sauces, gravies)
- A palm-sized portion of meat/fish = ~85-100g
- One piece of fruit (apple/orange) = ~150g
- One slice of bread = ~30g
- One plate of rice (Indonesian 'piring') = 150-200g MAX -- do NOT estimate more than 200g of rice per person per meal
- If you cannot see the portion clearly, note it as 'unable to determine -- estimated'

MAXIMUM PORTION CAPS -- do not exceed these under any circumstances:
  - Rice dish (nasi goreng, nasi putih, nasi rendang, nasi kari): 250g total per person
  - Fried rice (nasi goreng, mie goreng): 200g MAX for the rice component
  - Soup / bowl (soto, soto ayam, sup, mie kuwe): 400g total (bowl)
  - Noodle dish (mie, bihun, kwetiau): 300g total
  - Satay (sate): 100g meat MAX (4-6 skewers typical)
  - Gado-gado / salad: 250g total (vegetables + sauce)
  - Rendang / curry: 200g total (meat + sauce)
  - A full single plate meal: never exceed 500g total for ALL items combined
  - If your estimated portion for ANY item exceeds the cap above, USE THE CAP instead. Nutrition accuracy depends on realistic portions, not maximum estimates.

IDENTIFICATION RULES:
- Be as specific as possible: not just "rice" but "steamed white rice (nasi putih)"
- Not just "curry" but "chicken curry (kari ayam)" or "rendang"
- Include the preparation method if visible: fried, steamed, grilled, etc.
- List a dish AS ONE ENTRY -- do NOT decompose a dish into rice+protein+sauce separately
- If you're uncertain between two items, list the most likely one and note alternatives
- Do NOT invent items you cannot see -- only report what is actually in the image
- Indonesian foods are common -- watch for: nasi goreng, mie goreng, soto, rendang, satay, gado-gado, tempeh, tahu, sambal
- CRITICAL -- Indon vs Thai distinction: If the dish LOOKS like soto (yellow/herbal broth, rice noodles, bean sprouts), ALWAYS call it "soto" NOT "khao soi" (which is Thai). If it looks like pad thai, call it "mie goreng" NOT "pad thai". Indonesian cuisine uses yellow broth (kunyit/turmeric) and rice noodles -- Thai dishes use egg noodles and coconut milk. Default to Indonesian names when in doubt.
- Beverages: note if visible (coffee, tea, juice, water) and estimate volume
- Do NOT respond with Chinese characters (no \u4e00-\u9fff range) -- use English or Indonesian names only"""


# ── Image Preprocessing ────────────────────────────────────────────────────────

def _preprocess_image(image_bytes: bytes, max_pixels: int = 768) -> bytes:
    """
    Resize image to max_pixels on longest edge, convert to JPEG quality 85.
    Gemini 1.5 Flash handles 768px images well and this reduces payload size.
    """
    img = Image.open(BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Resize if too large
    longest = max(img.width, img.height)
    if longest > max_pixels:
        ratio = max_pixels / longest
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    output = BytesIO()
    img.save(output, format="JPEG", quality=85)
    return output.getvalue()


# ── Token Fetch (for direct API calls) ────────────────────────────────────────

def _get_access_token() -> str:
    """Get OAuth2 access token for direct Gemini API calls."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


# ── Core Analysis ──────────────────────────────────────────────────────────────

def analyze_meal_image(image_bytes: bytes) -> tuple[list[dict], Optional[float]]:
    """
    Analyze a meal photo using Vertex AI Gemini 1.5 Flash (via google.genai SDK).
    Returns (foods_list, total_grams_estimate) where total_grams is the model's
    own top-level estimate for the full plate (useful for sanity-checking sums).
    """
    if not GCP_PROJECT and not GEMINI_API_KEY:
        raise RuntimeError(
            "Neither GCP_PROJECT nor GOOGLE_API_KEY is set. "
            "Set one to use Gemini vision."
        )

    # Preprocess image (reduces size, improves reliability)
    image_bytes = _preprocess_image(image_bytes)

    # ── Route: google.genai SDK (service account) or Direct Gemini REST API ────

    if GCP_PROJECT and not GEMINI_API_KEY:
        # Vertex AI via google.genai SDK (uses service account on Cloud Run)
        # Uses ADC: credentials picked up from metadata server on Cloud Run
        import google.genai as genai_module
        client = genai_module.Client(
            vertexai=True,
            project=GCP_PROJECT,
            location=GCP_LOCATION,
            credentials=credentials,
        )
        image_part = {
            "inline_data": {
                "data": base64.b64encode(image_bytes).decode(),
                "mime_type": "image/jpeg",
            }
        }
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image_part],
            config={
                "system_instruction": SYSTEM_PROMPT,
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "foods": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "portion_description": {"type": "string"},
                                    "portion_grams_estimate": {"type": "number"},
                                    "confidence": {"type": "number"},
                                },
                                "required": ["name", "description", "portion_grams_estimate", "confidence"],
                            },
                        },
                        "total_grams_estimate": {"type": "number"},
                        "overall_confidence": {"type": "number"},
                        "notes": {"type": "string"},
                    },
                    "required": ["foods", "total_grams_estimate", "overall_confidence"],
                },
                "temperature": 0.1,
                "seed": 42,
                "max_output_tokens": 4096,
            },
        )
        raw_text = response.text

    else:
        # Direct Gemini REST API (for local dev with API key)
        import requests as _requests

        token = _get_access_token() if not GEMINI_API_KEY else None
        image_b64 = base64.b64encode(image_bytes).decode()

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_b64,
                        }
                    }
                ]
            }],
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "generation_config": {
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "foods": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "portion_description": {"type": "string"},
                                    "portion_grams_estimate": {"type": "number"},
                                    "confidence": {"type": "number"},
                                },
                                "required": ["name", "description", "portion_grams_estimate", "confidence"],
                            },
                        },
                        "total_grams_estimate": {"type": "number"},
                        "overall_confidence": {"type": "number"},
                        "notes": {"type": "string"},
                    },
                    "required": ["foods", "total_grams_estimate", "overall_confidence"],
                },
                "temperature": 0.1,
                "seed": 42,
                "max_output_tokens": 4096,
            },
        }

        api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash"
            f":generateContent?key={GEMINI_API_KEY}"
        )

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        resp = _requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

    # ── Parse JSON response ─────────────────────────────────────────────────────
    foods, total_grams = _parse_gemini_response(raw_text)

    return foods, total_grams


def _parse_gemini_response(raw_text: str) -> list[dict]:
    """
    Parse Gemini's JSON response. Handles:
    - Raw JSON dict with 'foods' key
    - JSON embedded in markdown code blocks
    - Malformed JSON with trailing text
    """
    # Strip markdown code fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        # Remove triple-backtick wrapper
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract the JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                raise ValueError(f"Could not parse Gemini response: {raw_text[:200]}")
        else:
            raise ValueError(f"No JSON found in Gemini response: {raw_text[:200]}")

    foods_raw = data.get("foods", [])
    results = []
    for item in foods_raw:
        results.append({
            "name": item.get("name", "Unknown"),
            "description": item.get("description", ""),
            "portion_grams_estimate": float(item.get("portion_grams_estimate", 0)),
            "confidence": float(item.get("confidence", 0.5)),
        })

    # Extract top-level total for sanity-checking portion sums
    total_grams = data.get("total_grams_estimate")

    return results, total_grams
