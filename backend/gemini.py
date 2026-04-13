"""
backend/gemini.py — Vision Integration via GCP Cloud Vision API

Uses Google Cloud Vision API (Label Detection + Object Localization)
to identify foods in meal photos, then matches against the nutrition DB.
"""
import base64
import os
from typing import Optional

import google.auth
import requests

GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GCP_PROJECT_ID", ""))
VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"

# Food-related label keywords (Cloud Vision returns these for food images)
# Matches against label descriptions to filter food items
FOOD_KEYWORDS = {
    # Indonesian staples
    "rice", "nasi", "noodle", "mie", "soup", "fried", "grilled",
    "satay", "sate", "curry", "sambal", "coconut", "coconut milk",
    "chicken", "beef", "pork", "fish", "shrimp", "prawn", "tofu",
    "tempeh", "egg", "vegetable", "salad", "fruit", "banana",
    "mango", "pineapple", "jackfruit", "durian", "papaya",
    # General food
    "food", "meal", "dish", "cuisine", "eating", "plate", "bowl",
    "bread", "pizza", "burger", "sandwich", "pasta", "rice bowl",
    "stew", "gratin", "roast", "steak", "sushi", "ramen", "pho",
    "taco", "nachos", "kebab", "falafel", "dumpling", "spring roll",
    "ice cream", "dessert", "cake", "cookie", "pastry", "chocolate",
    "coffee", "tea", "juice", "smoothie", "drink", "beverage",
    "fried rice", "fried noodle", "laksa", "rendang", "soto",
    "gado", "gado gado", "pecel", "kangkung", "bayam", "kecap",
    "soy sauce", "fish sauce", "chili", "garlic", "ginger",
    "breaded", "crispy", "steamed", "boiled", "smoked", "dried",
    "organic", "fresh", "raw", "cooked", "hot", "cold",
    # Fruits & produce
    "apple", "orange", "lemon", "lime", "avocado", "tomato",
    "cucumber", "lettuce", "spinach", "carrot", "broccoli",
    "potato", "corn", "beans", "mushroom", "onion", "pepper",
    # Desserts & sweets
    "es", "es cendol", "es teler", "bubur", "klepon", "lapis",
    "kue", "roti", "tahu", "tahu goreng", "tahur", "kerak",
}

# Non-food labels to exclude
NON_FOOD_LABELS = {
    "electronics", "device", "phone", "computer", "screen", "furniture",
    "clothing", "shoes", "bag", "car", "building", "landscape",
    "sky", "cloud", "grass", "tree", "flower", "beach", "mountain",
    "person", "people", "selfie", "hand", "face", "skin", "hair",
    "text", "font", "screenshot", "diagram", "logo", "brand",
}


def _get_token() -> str:
    """
    Get OAuth2 access token using google.auth.default().
    Works in Cloud Run (metadata server) and locally (ADC/service account).
    """
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def _call_vision_api(image_bytes: bytes) -> list[dict]:
    """
    Call Cloud Vision API with both LABEL_DETECTION and OBJECT_LOCALIZATION.
    Returns a list of detected items with description and score.
    """
    token = _get_token()
    image_content = base64.b64encode(image_bytes).decode()

    payload = {
        "requests": [{
            "image": {"content": image_content},
            "features": [
                {"type": "LABEL_DETECTION", "maxResults": 20},
                {"type": "OBJECT_LOCALIZATION", "maxResults": 15},
            ],
        }]
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        VISION_API_URL,
        headers=headers,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    # Handle edge case where responses is null/missing
    responses = data.get("responses")
    if not responses:
        return []

    first = responses[0] if responses else {}

    results = []

    # Parse label annotations
    for label in first.get("labelAnnotations", []):
        results.append({
            "description": label.get("description", "").lower(),
            "score": label.get("score", 0),
            "source": "label",
        })

    # Parse localized objects
    for obj in first.get("localizedObjectAnnotations", []):
        results.append({
            "description": obj.get("name", "").lower(),
            "score": obj.get("score", 0),
            "source": "object",
        })

    return results


def _is_food(description: str, score: float) -> bool:
    """Check if a detected label is food-related and confident enough."""
    if score < 0.3:
        return False
    desc_lower = description.lower()

    # Exclude non-food
    if any(excluded in desc_lower for excluded in NON_FOOD_LABELS):
        return False

    # Include if it matches food keywords or is a general food term
    return any(kw in desc_lower for kw in FOOD_KEYWORDS) or desc_lower in FOOD_KEYWORDS


def analyze_meal_image(image_bytes: bytes) -> list[dict]:
    """
    Analyze a meal photo using Cloud Vision API.

    Args:
        image_bytes: Raw JPEG image bytes

    Returns:
        List of dicts: [{"name": "...", "description": "...", "confidence": 0.85}, ...]
    """
    if not GCP_PROJECT:
        raise RuntimeError("GCP_PROJECT environment variable not set")

    # Call Cloud Vision
    detections = _call_vision_api(image_bytes)

    # Filter to food-related items
    food_items = []
    seen = set()

    for item in sorted(detections, key=lambda x: x["score"], reverse=True):
        desc = item["description"]
        score = item["score"]

        if not desc:
            continue

        # Deduplicate
        if desc in seen:
            continue
        seen.add(desc)

        if _is_food(desc, score):
            food_items.append({
                "name": desc.title(),
                "description": f"Detected via {item['source']}",
                "confidence": round(score, 2),
            })

    return food_items
