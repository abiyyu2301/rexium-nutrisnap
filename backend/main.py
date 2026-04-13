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

from vertexai import analyze_meal_image
from nutrition import NutritionDB

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


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(file: UploadFile = File(...)):
    # 1. Validate
    try:
        image_bytes = await file.read()
    except Exception:
        raise HTTPException(400, "Could not read uploaded file")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 10MB)")

    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    # 2. Preprocess
    image_bytes = preprocess_image(image_bytes)

    # 3. Gemini vision
    try:
        raw_foods = analyze_meal_image(image_bytes)
    except Exception as e:
        raise HTTPException(500, f"Vision API error: {str(e)}")

    if not raw_foods:
        raise HTTPException(400, "No food detected in image")

    # 4. Match against nutrition DB
    identified = []
    for item in raw_foods:
        name = item.get("name", "")
        confidence = float(item.get("confidence", 0.5))

        # Fuzzy search in Firestore
        matches = db.search_foods(name, limit=3)

        if matches:
            best = matches[0]
            identified.append(IdentifiedFood(
                raw_name=name,
                matched_id=best.get("id"),
                matched_name=best.get("food_name"),
                calories_kcal=best.get("calories_kcal"),
                protein_g=best.get("protein_g"),
                carbs_g=best.get("carbs_g"),
                fat_g=best.get("fat_g"),
                fiber_g=best.get("fiber_g"),
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
