"""
backend/vertexai.py — Gemini Vision Integration
Uses GCP Vertex AI to identify foods in meal photos.
"""
import json
import os
import re
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel, Part

GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GCP_PROJECT_ID", ""))
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")

# Initialize Vertex AI (credentials from service account)
try:
    vertexai.init(project=GCP_PROJECT, location=GCP_LOCATION)
except Exception:
    pass  # Will retry on first call

PROMPT = """
You are a nutrition analysis assistant for Indonesian cuisine.
Analyze this meal photo and identify each distinct food item visible.

For each item provide:
1. Food name (Indonesian preferred, e.g. "Nasi goreng", "Sate ayam", "Gado-gado")
2. Brief description of preparation if visible (grilled, fried, soup, steamed, etc.)
3. Your confidence the identification is correct (0.0 to 1.0)

Return ONLY valid JSON — no markdown formatting, no explanation:
{"foods": [{"name": "...", "description": "...", "confidence": 0.0}]}

Rules:
- Identify ALL visible food items individually
- Count each distinct food as a separate item (nasi goreng + ayam = 2 items)
- If a food is unidentifiable, omit it — do not guess
- Low confidence items (below 0.6) should still be named but marked honestly
- Be specific about Indonesian dishes; use common Indonesian food names
"""


def analyze_meal_image(image_bytes: bytes, model_name: str = "gemini-2.0-flash") -> list[dict]:
    """
    Send meal image to Gemini and return list of identified foods.

    Args:
        image_bytes: Raw JPEG image bytes
        model_name: Gemini model to use (default: gemini-2.0-flash)

    Returns:
        List of dicts: [{"name": "...", "description": "...", "confidence": 0.85}, ...]
    """
    if not GCP_PROJECT:
        raise RuntimeError("GCP_PROJECT environment variable not set")

    model = GenerativeModel(model_name)

    image_part = Part.from_data(data=image_bytes, mime_type="image/jpeg")

    response = model.generate_content(
        [image_part, PROMPT],
        generation_config={
            "temperature": 0.1,  # Low temp for consistent food ID
            "max_output_tokens": 512,
        }
    )

    text = response.text
    return _parse_response(text)


def _parse_response(text: str) -> list[dict]:
    """Parse Gemini's JSON response with fallback for malformed output."""
    # Gemini sometimes wraps in markdown
    text = re.sub(r"^```json\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())

    try:
        data = json.loads(text)
        foods = data.get("foods", [])
        # Validate structure
        return [
            {
                "name": str(f.get("name", "")),
                "description": str(f.get("description", "")),
                "confidence": float(f.get("confidence", 0.5)),
            }
            for f in foods
            if f.get("name")
        ]
    except (json.JSONDecodeError, ValueError, TypeError):
        # Attempt partial extraction
        foods = re.findall(r'"name"\s*:\s*"([^"]+)"', text)
        if foods:
            return [{"name": f, "description": "", "confidence": 0.5} for f in foods]
        raise ValueError(f"Could not parse Gemini response: {text[:200]}")
