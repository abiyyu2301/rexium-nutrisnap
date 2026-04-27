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

SYSTEM_PROMPT = """You are NutriSnap, an expert food identification AI.
Your task is to identify all distinct food and drink items in the meal photo.

CRITICAL RULES:
- List EVERY distinct food item you can identify — do not skip minor ingredients
- Be as specific as possible: "nasi goreng" not just "rice", "tahu goreng" not just "tofu"
- Indonesian dishes are common: nasi goreng, mie goreng, soto, rendang, satay, gado-gado, tempeh, tahu, sambal
- For each item: name it in the language it is most commonly known (English or Indonesian)
- Do NOT estimate portions, calories, or nutrition — only identify what the food IS
- Do NOT respond with Chinese characters (no \\u4e00-\\u9fff range)
- If you cannot identify an item, say "unknown food item" — do not guess

OUTPUT FORMAT -- respond ONLY with valid JSON in this exact structure:
{
  "foods": [
    {
      "name": "specific food name in English or Indonesian",
      "confidence": number between 0.0 and 1.0
    }
  ],
  "notes": "any observations about image quality or ambiguity"
}

EXAMPLES OF GOOD OUTPUTS:
- {"foods":[{"name":"nasi goreng","confidence":0.95},{"name":"tahu goreng","confidence":0.9}],"notes":""}
- {"foods":[{"name":"banana","confidence":0.85},{"name":"maple syrup","confidence":0.9}],"notes":"pancake breakfast"}
- {"foods":[{"name":"soto ayam","confidence":0.95},{"name":"nasi putih","confidence":0.9}],"notes":""}
"""


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

def analyze_meal_image(image_bytes: bytes, user_description: Optional[str] = None) -> tuple[list[dict], Optional[float]]:
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

    # ── Direct Vertex AI REST API ───────────────────────────────────────────────
    # Service account (Cloud Run): google.auth.default() → bearer token
    # Local dev: GEMINI_API_KEY env var → direct Gemini API
    # The google.genai SDK path was removed — direct REST is more reliable.
    import requests as _requests

    token = None
    if GEMINI_API_KEY:
        api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash"
            f":generateContent?key={GEMINI_API_KEY}"
        )
    else:
        # Vertex AI via service account — get bearer token from ADC
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        token = creds.token
        # Route through us-central1 (always supported) or asia-southeast1
        api_url = (
            f"https://us-central1-aiplatform.googleapis.com/v1beta1/"
            f"projects/rexium-nutrisnap/locations/us-central1/"
            f"publishers/google/models/gemini-2.0-flash:generateContent"
        )

    image_b64 = base64.b64encode(image_bytes).decode()

    # Build user parts: image + optional description
    user_parts = [
        {
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": image_b64,
            }
        }
    ]
    if user_description:
        user_parts.append({
            "text": (
                f"USER DESCRIPTION (use this to resolve ambiguous lookalike dishes):\n"
                f"{user_description}\n\n"
                f"When the user provides specific foods and/or gram amounts below, "
                f"prioritize those items in your detection and lean toward matching "
                f"what they described rather than relying solely on visual appearance."
            )
        })

    payload = {
        "contents": [{
            "role": "user",
            "parts": user_parts
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
                                "confidence": {"type": "number"},
                            },
                            "required": ["name", "confidence"],
                        },
                    },
                    "notes": {"type": "string"},
                },
                "required": ["foods", "notes"],
            },
            "temperature": 0.05,      # Very low for consistency
            "max_output_tokens": 4096,
        },
    }

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = _requests.post(api_url, headers=headers, json=payload, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

    # ── Parse JSON response ─────────────────────────────────────────────────────
    foods = _parse_gemini_response(raw_text)

    return foods


def _parse_gemini_response(raw_text: str) -> list[dict]:
    """
    Parse Gemini's JSON response. Returns list of {name, confidence}.
    Handles: raw JSON, markdown code blocks, malformed JSON.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
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
    return [
        {
            "name": item.get("name", "Unknown"),
            "confidence": float(item.get("confidence", 0.5)),
        }
        for item in foods_raw
    ]
