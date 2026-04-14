"""
backend/main.py — FastAPI NutriSnap Backend
POST /analyze     — Analyze meal image via Gemini vision
GET  /foods/search — Search nutrition DB by name
GET  /health      — Health check
"""
import os
import json
import uuid
import re
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gemini import analyze_meal_image
from nutrition import NutritionDB
import base64
import google.auth
import requests

app = FastAPI(title="NutriSnap API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GCS_BUCKET = os.getenv("GCS_BUCKET", "rexium-nutrisnap-images")
db = NutritionDB()


# ── Request/Response Schemas ────────────────────────────────────────────────

class IdentifiedFood(BaseModel):
    raw_name: str
    matched_id: Optional[str]
    matched_name: Optional[str]
    calories_kcal: Optional[float]
    protein_g: Optional[float]
    carbs_g: Optional[float]
    fat_g: Optional[float]
    fiber_g: Optional[float]
    confidence: float
    source: Optional[str] = None

class NutritionSummary(BaseModel):
    total_calories_kcal: float
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    total_fiber_g: float

class AnalysisResponse(BaseModel):
    success: bool
    analysis_id: str
    identified_foods: list[IdentifiedFood]
    nutrition_summary: NutritionSummary


# ── Image Preprocessing ────────────────────────────────────────────────────

def validate_image(file: UploadFile) -> bytes:
    """Read and validate uploaded image file."""
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 10MB)")
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 10MB)")
    return data


def preprocess_image(image_bytes: bytes) -> bytes:
    """Resize image to max 1024px width, convert to JPEG, strip EXIF."""
    from PIL import Image
    img = Image.open(BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    # Resize to max 1024px width
    max_w = 1024
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
    output = BytesIO()
    img.save(output, format="JPEG", quality=85)
    return output.getvalue()


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/test-gemini")
async def test_gemini(model: str = "gemini-2.5-flash"):
    """Test Gemini access via Vertex AI REST API."""
    import google.auth
    import requests

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    token = credentials.token

    results = {}
    # asia-southeast1 is the configured location; us-central1 as fallback
    for location in ["asia-southeast1", "us-central1"]:
        endpoint = f"https://{location}-aiplatform.googleapis.com/v1/projects/rexium-nutrisnap/locations/{location}/publishers/google/models/{model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Reply: OK"}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 10},
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            data = resp.json()
            if resp.status_code == 200:
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                results[location] = {"status": "ok", "response": text}
                return results[location]
            else:
                results[location] = {"status": resp.status_code, "error": str(data)[:120]}
        except Exception as e:
            results[location] = {"status": "error", "error": str(e)[:80]}

    return {"status": "all_failed", "attempts": results}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(image: UploadFile = File(...)):
    # 1. Validate
    try:
        image_bytes = await image.read()
    except Exception:
        raise HTTPException(400, "Could not read uploaded file")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 10MB)")

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed:
        raise HTTPException(400, f"Unsupported file type: {image.content_type}")

    # 2. Preprocess
    try:
        image_bytes = preprocess_image(image_bytes)
    except Exception as e:
        raise HTTPException(400, f"Invalid image data: {str(e)}")

    # 3. Gemini vision
    try:
        raw_foods = analyze_meal_image(image_bytes)
    except Exception as e:
        raise HTTPException(500, f"Vision API error: {str(e)}")

    if not raw_foods:
        raise HTTPException(400, "No food detected in image")

    # 4. Match against nutrition DB
    # Labels that are too generic to reliably match to nutrition data
    GENERIC_LABELS = {
        "food", "meal", "dish", "cuisine", "eating", "plate", "bowl",
        "side dish", "side", "main dish", "staple food", "fast food",
        "snack", "appetizer", "entree", "course", "food group",
        "dishware", "plate", "cutlery", "tableware",
        "spice", "ingredient", "料理",  # Chinese/Japanese
    }

    # Blocklist: nutrition DB entries that are bad matches for generic food labels
    BLOCKLIST_KEYWORDS = {"oil", "fat", "sugar", "syrup", "margarine", "shortening"}

    identified = []
    for item in raw_foods:
        name = item.get("name", "").lower()
        confidence = float(item.get("confidence", 0.5))
        portion_grams = float(item.get("portion_grams_estimate", 100))

        # Skip very generic labels
        if name in GENERIC_LABELS or len(name) < 3:
            continue

        # Skip generic labels with low confidence
        if confidence < 0.5 and name in {"vegetable", "fruit", "protein", "carb"}:
            continue

        # Fuzzy search in Firestore
        matches = db.search_foods(name.title(), limit=3)

        if matches:
            best = matches[0]
            best_name = best.get("food_name", "").lower()

            # Skip bad blocklist matches for generic labels
            if name in {"vegetable", "leaf vegetable", "fruit"}:
                if any(b in best_name for b in BLOCKLIST_KEYWORDS):
                    continue

            # Scale nutrition by portion (data is per 100g)
            portion_scale = portion_grams / 100.0

            identified.append(IdentifiedFood(
                raw_name=name,
                matched_id=best.get("id"),
                matched_name=best.get("food_name"),
                calories_kcal=round(best.get("calories_kcal", 0) * portion_scale, 1),
                protein_g=round(best.get("protein_g", 0) * portion_scale, 1),
                carbs_g=round(best.get("carbs_g", 0) * portion_scale, 1),
                fat_g=round(best.get("fat_g", 0) * portion_scale, 1),
                fiber_g=round((best.get("fiber_g") or 0) * portion_scale, 1),
                confidence=round(confidence, 2),
                source=best.get("source"),
            ))
        else:
            # No match found — still report it but with null nutrition
            identified.append(IdentifiedFood(
                raw_name=name,
                matched_id=None,
                matched_name=None,
                calories_kcal=None,
                protein_g=None,
                carbs_g=None,
                fat_g=None,
                fiber_g=None,
                confidence=round(confidence, 2),
                source=None,
            ))

    # 5. Compute totals
    matched = [f for f in identified if f.calories_kcal is not None]
    summary = NutritionSummary(
        total_calories_kcal=round(sum(f.calories_kcal for f in matched), 1),
        total_protein_g=round(sum((f.protein_g or 0) for f in matched), 1),
        total_carbs_g=round(sum((f.carbs_g or 0) for f in matched), 1),
        total_fat_g=round(sum((f.fat_g or 0) for f in matched), 1),
        total_fiber_g=round(sum((f.fiber_g or 0) for f in matched), 1),
    )

    analysis_id = str(uuid.uuid4())

    return AnalysisResponse(
        success=True,
        analysis_id=analysis_id,
        identified_foods=identified,
        nutrition_summary=summary,
    )


@app.get("/foods/search")
async def search_foods(q: str = Query(..., min_length=1)):
    results = db.search_foods(q, limit=10)
    return {"query": q, "count": len(results), "results": results}
