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
        raw_foods, total_grams = analyze_meal_image(image_bytes)
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

    # Compound name splitter: split "nasi ayam kecap" or "hainanese chicken rice dark soy sauce"
    # into individual ingredients for separate matching
    COMPOUND_SEPARATORS = [
        " with ", " and ", " + ", ", ", " / ", " plus ",
    ]

    def _split_compound(name: str) -> list[str]:
        """Split a compound food name into individual ingredient parts."""
        name_lower = name.lower()
        parts = [name_lower]
        # Try splitting on known separators
        for sep in COMPOUND_SEPARATORS:
            if sep in name_lower:
                split_parts = [p.strip() for p in name_lower.split(sep) if p.strip()]
                if len(split_parts) >= 2:
                    parts = split_parts
                    break
        # Also detect embedded sauces/toppings: "X with Y sauce" → ["X", "Y sauce"]
        import re
        sauce_match = re.search(r"(.+?)\s+(?:with\s+)?(.+?)\s+sauce", name_lower)
        if sauce_match:
            main = sauce_match.group(1).strip()
            sauce = (sauce_match.group(2).strip() + " sauce").strip()
            parts = [p.strip() for p in [main, sauce] if p.strip()]
        return parts

    # ── FIX 1: Always search the FULL name first, before splitting ──────────
    # This prevents perfect dish-name matches from being lost to aggressive splitting.
    # Only fall back to splitting when the full name scores poorly.
    #
    # FIX 2: When a generic vegetable term gets a high-calorie wrong match,
    # skip it and prefer known vegetable entries with realistic low calories.
    # ─────────────────────────────────────────────────────────────────────────

    GENERIC_VEGETABLE_TERMS = {
        "mixed salad greens", "salad greens", "mixed greens", "green salad",
        "leaf vegetable", "leafy green", "mixed vegetables", "vegetable",
        "sayur", "sayuran", "salad", "greens", "mixed vegetable",
    }
    # Blocklist: DB entries that are bad matches for generic vegetable queries
    # (these are unrelated high-calorie items that happen to share generic tokens)
    VEGETABLE_BLOCKLIST = {
        "tuna_salad", "egg_salad", "chicken_salad", "tuna", "egg",
        "mayonnaise", "mayo", "tuna salad", "tuna_,_salad",
    }

    # Server-side portion clamping (safety net — Gemini may still overestimate)
    # Hard caps per dish category in grams. Applied after Gemini returns estimates.
    PORTION_CAPS = {
        # (keyword substring -> max grams)  — first match wins
        "nasi goreng": 220,
        "nasi putih": 200,
        "nasi": 250,          # generic rice dishes
        "fried rice": 220,
        "soto": 400,          # bowl soups
        "mie goreng": 300,     # fried noodles
        "mie": 300,           # general noodles
        "bihun": 250,         # rice noodles
        "kwetiau": 300,       # wide noodles
        "sate": 120,          # satay (4-6 skewers)
        "satay": 120,
        "rendang": 200,       # rendang + curry
        "kari": 200,
        "gulai": 200,
        "gado": 280,          # gado-gado
        "salad": 250,
        "telur": 60,          # eggs (1-2 pieces)
        "egg": 60,
        "tahu": 80,           # tofu portions
        "tempe": 80,
        "sambal": 20,        # sauces — small
        "bumbu": 20,
        "kecap": 15,
        "peanut sauce": 30,   # peanut sauce is dense, small portion
        "bawang goreng": 15,  # fried shallots garnish
        "white rice": 200,
        "steamed rice": 200,
    }

    def _clamp_portion(name: str, grams: float) -> float:
        """Apply dish-category portion cap. Returns clamped value."""
        name_lower = name.lower()
        for keyword, cap in PORTION_CAPS.items():
            if keyword in name_lower:
                return min(grams, cap)
        # Default: if Gemini says >400g for an unidentified item, cap it
        if grams > 400:
            return min(grams, 250)
        return grams

    identified = []
    for item in raw_foods:
        name = item.get("name", "").lower()
        confidence = float(item.get("confidence", 0.5))
        portion_grams_raw = float(item.get("portion_grams_estimate", 100))
        portion_grams = _clamp_portion(name, portion_grams_raw)

        # Skip very generic labels
        if name in GENERIC_LABELS or len(name) < 3:
            continue

        # Skip generic labels with low confidence
        if confidence < 0.5 and name in {"vegetable", "fruit", "protein", "carb"}:
            continue

        # FIX 1a: Search the FULL compound name FIRST (before splitting).
        # Only use split parts if the full name scores poorly (score < 0.75).
        full_name_search = name.title()
        full_matches = db.search_foods(full_name_search, limit=5)
        use_split = True
        if full_matches:
            top_score = full_matches[0].get("score", 0)
            top_name = full_matches[0].get("food_name", "").lower()
            # If top match is a strong score AND the matched name is a reasonable
            # superstring/substring of the query, accept it without splitting
            if top_score >= 0.85 and (top_name in name or name in top_name):
                use_split = False

        if use_split:
            ingredient_names = _split_compound(name)
        else:
            # Full name matched well — treat the whole dish as one ingredient
            ingredient_names = [name]

        # Portion allocation: when splitting a compound dish, distribute the total
        # portion across ingredients. Base sauces/toppings get small fixed portions
        # rather than a proportional share.
        SAUCE_GRAM_ESTIMATE = 15  # typical dipping sauce portion
        TOPPING_GRAM_ESTIMATE = 30  # typical topping portion

        num_ingredients = len(ingredient_names)
        # For sauces/toppings in compound names, use a fixed small portion
        # rather than the full dish portion
        if num_ingredients >= 2:
            # Check which parts look like sauces/toppings
            SAUCE_INDICATORS = {"sauce", "dipping", "chili", "soy", "kecap", " sambal", "cabe", "cabai"}
            allocated = []
            remaining_grams = portion_grams
            for i, ing in enumerate(ingredient_names):
                is_sauce = any(s in ing for s in SAUCE_INDICATORS)
                if is_sauce and i > 0:  # sauce is rarely the main dish
                    allocated_grams = SAUCE_GRAM_ESTIMATE
                else:
                    # Main dish gets the rest
                    other_sauces = sum(1 for j, x in enumerate(ingredient_names) if j != i and any(s in x for s in SAUCE_INDICATORS))
                    allocated_grams = max(remaining_grams - (other_sauces * SAUCE_GRAM_ESTIMATE), 50)
                allocated.append(allocated_grams)
        else:
            allocated = [portion_grams]

        # Search for each ingredient separately
        seen_ids = set()
        for idx, ingredient_name in enumerate(ingredient_names):
            if ingredient_name in seen_ids:
                continue
            seen_ids.add(ingredient_name)

            # Skip if too generic
            if ingredient_name in GENERIC_LABELS or len(ingredient_name) < 3:
                continue

            ing_portion = allocated[idx] if idx < len(allocated) else portion_grams

            # FIX 1b: Search the full ingredient name (not split) first
            ing_search_name = ingredient_name.title()
            matches = db.search_foods(ing_search_name, limit=3)
            if not matches:
                continue

            best = matches[0]
            best_id = best.get("id", "")
            best_name = best.get("food_name", "").lower()
            best_cal_per_100 = best.get("calories_kcal") or 0

            # FIX 2: Generic vegetable → avoid wrong high-calorie matches.
            # If the match is a generic vegetable term but the DB entry is
            # suspiciously high-calorie (>120 kcal/100g) AND matches a
            # blocklisted non-vegetable entry, skip it and try more specific terms.
            is_generic_veg = ingredient_name in GENERIC_VEGETABLE_TERMS
            is_blocklisted = any(b in best_id or b in best_name for b in VEGETABLE_BLOCKLIST)
            if is_generic_veg and is_blocklisted and best_cal_per_100 > 120:
                # Try searching with explicit "sayur" / "selada" / "vegetable" suffix
                for alt_term in ["selada", "sayur", "lettuce", "bayam", "kubis"]:
                    alt_matches = db.search_foods(alt_term, limit=5)
                    for alt in alt_matches:
                        alt_cal = alt.get("calories_kcal") or 0
                        alt_name = alt.get("food_name", "").lower()
                        alt_id = alt.get("id", "")
                        alt_blocked = any(b in alt_id or b in alt_name for b in VEGETABLE_BLOCKLIST)
                        # Accept if: low calories AND not blocklisted
                        if alt_cal < 100 and not alt_blocked:
                            best = alt
                            best_id = alt_id
                            best_name = alt_name
                            best_cal_per_100 = alt_cal
                            break
                    else:
                        continue
                    break

            # Skip bad blocklist matches for generic labels
            if ingredient_name in {"vegetable", "leaf vegetable", "fruit"}:
                if any(b in best_name for b in BLOCKLIST_KEYWORDS):
                    continue

            # Scale nutrition by portion (data is per 100g)
            portion_scale = ing_portion / 100.0

            identified.append(IdentifiedFood(
                raw_name=ingredient_name,
                matched_id=best.get("id"),
                matched_name=best.get("food_name"),
                calories_kcal=round((best.get("calories_kcal") or 0) * portion_scale, 1),
                protein_g=round((best.get("protein_g") or 0) * portion_scale, 1),
                carbs_g=round((best.get("carbs_g") or 0) * portion_scale, 1),
                fat_g=round((best.get("fat_g") or 0) * portion_scale, 1),
                fiber_g=round((best.get("fiber_g") or 0) * portion_scale, 1),
                confidence=round(confidence, 2),
                source=best.get("source"),
            ))

    # Deduplicate by matched_id, keeping the best (highest confidence) match
    deduped_map = {}
    for food in identified:
        mid = food.matched_id
        if mid not in deduped_map or food.confidence > deduped_map[mid].confidence:
            deduped_map[mid] = food
    identified = list(deduped_map.values())

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
