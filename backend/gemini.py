"""
backend/gemini.py — Vertex AI Gemini 1.5 Flash Vision Integration

Two-step approach:
  Step 1: Gemini 1.5 Flash identifies foods and estimates portions from image
  Step 2: main.py matches food names against the Firestore nutrition DB

Authentication via:
  - Service account (Cloud Run / VM): google.auth.default() — no key needed
  - Local dev: GOOGLE_API_KEY env var (direct Gemini API)
"""
import base64
import json
import os
import re
from io import BytesIO
from typing import Optional

import google.auth
import vertexai
from PIL import Image
from vertexai.generative_models import GenerativeModel, Part

# ── Vertex AI Init ────────────────────────────────────────────────────────────

GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GCP_PROJECT_ID", ""))
GCP_LOCATION = os.getenv("GCP_LOCATION", "asia-southeast1")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Initialize Vertex AI (uses service account on Cloud Run)
if GCP_PROJECT and not GEMINI_API_KEY:
    vertexai.init(project=GCP_PROJECT, location=GCP_LOCATION)


# ── System + User Prompts ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are NutriSnap, an expert food identification and nutrition estimation AI.
Your task is to analyze meal photos and identify all distinct food and drink items present.

For each item you identify, you must estimate the portion size using visual cues
(plate size, compare to fist/hand, typical serving conventions).

OUTPUT FORMAT — respond ONLY with valid JSON in this exact structure:
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
  "overall_confidence": number between 0.0 and 1.0,
  "notes": "any observations about image quality, lighting, or ambiguity"
}

PORTION ESTIMATION GUIDELINES:
- A standard dinner plate = ~250-300g total
- A fist = ~200g (use as reference for rice, noodles, etc.)
- A tablespoon = ~15g (for sauces, gravies)
- A palm-sized portion of meat/fish = ~85-100g
- One piece of fruit (apple/orange) = ~150g
- One slice of bread = ~30g
- A cup of rice (Indonesian 'piring') = ~200g
- If you cannot see the portion clearly, note it as 'unable to determine — estimated'

IDENTIFICATION RULES:
- Be as specific as possible: not just "rice" but "steamed white rice (nasi putih)"
- Not just "curry" but "chicken curry (kari ayam)" or "rendang"
- Include the preparation method if visible: fried, steamed, grilled, etc.
- If you're uncertain between two items, list the most likely one and note alternatives
- Do NOT invent items you cannot see — only report what is actually in the image
- Indonesian foods are common — watch for: nasi goreng, mie goreng, soto, rendang, satay, gado-gado, tempeh, tahu, sambal
- Beverages: note if visible (coffee, tea, juice, water) and estimate volume"""


# ── Image Preprocessing ───────────────────────────────────────────────────────

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
    """Get OAuth2 access token for Vertex AI API calls."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


# ── Core Analysis ──────────────────────────────────────────────────────────────

def analyze_meal_image(image_bytes: bytes) -> list[dict]:
    """
    Analyze a meal photo using Vertex AI Gemini 1.5 Flash.

    Args:
        image_bytes: Raw JPEG image bytes.

    Returns:
        List of dicts: [{"name": "...", "description": "...", "portion_grams_estimate": 150, "confidence": 0.92}, ...]
    """
    if not GCP_PROJECT and not GEMINI_API_KEY:
        raise RuntimeError(
            "Neither GCP_PROJECT nor GOOGLE_API_KEY is set. "
            "Set one to use Gemini vision."
        )

    # Preprocess image (reduces size, improves reliability)
    image_bytes = _preprocess_image(image_bytes)

    # ── Route: Vertex AI (service account) or Direct Gemini API ──────────────

    if GCP_PROJECT and not GEMINI_API_KEY:
        # Vertex AI via SDK (uses service account on Cloud Run)
        model = GenerativeModel(
            model_name="gemini-1.5-flash-002",
            system_instruction=[SYSTEM_PROMPT],
        )
        image_part = Part.from_data(
            data=image_bytes,
            mime_type="image/jpeg",
        )
        response = model.generate_content(
            [image_part],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.3,
                "max_output_tokens": 2048,
            },
        )
        raw_text = response.text

    else:
        # Direct Gemini API (for local dev with API key)
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
                "temperature": 0.3,
                "max_output_tokens": 2048,
            },
        }

        # Vertex AI REST endpoint
        vertex_url = (
            f"https://{GCP_LOCATION}-aiplatform.googleapis.com/v1/"
            f"projects/{GCP_PROJECT}/locations/{GCP_LOCATION}"
            f":publishDocuments"
        )
        # Actually for generateContent it's a different endpoint
        model_name = "gemini-1.5-flash-002"

        api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}"
            f":generateContent?key={GEMINI_API_KEY}"
        )

        headers = {
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        resp = _requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

    # ── Parse JSON response ──────────────────────────────────────────────────
    foods = _parse_gemini_response(raw_text)

    return foods


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

    return results
