"""
nutrition-data/patch_missing_foods.py

Adds 4 missing food entries to Firestore and sanitizes bad search_tokens
on existing USDA entries that were causing cross-contamination.

Run: python3 patch_missing_foods.py --project rexium-nutrisnap
"""
import argparse
from google.cloud import firestore
from google.auth import default


# ── New food entries to add ──────────────────────────────────────────────────

NEW_FOODS = [
    {
        "id": "tkpi_NEW_020",
        "food_name": "Sambal Kacang",
        "food_name_en": "Peanut Sauce (Sambal Kacang)",
        "calories_kcal": 290.0,
        "protein_g": 12.0,
        "carbs_g": 20.0,
        "fat_g": 19.0,
        "fiber_g": 4.0,
        "category": "sauce",
        "source": "tkpi_supplement",
        "food_name_lower": "sambal kacang",
        "food_name_en_lower": "peanut sauce (sambal kacang)",
        "search_tokens": [
            "sambal", "kacang", "peanut", "sauce", "bumbu", "peanut sauce",
            "sambal kacang", "kacang goreng", "bumbu kacang", "peanut_sauce",
        ],
    },
    {
        "id": "tkpi_NEW_021",
        "food_name": "Bawang Goreng",
        "food_name_en": "Fried Shallots (Bawang Goreng)",
        "calories_kcal": 200.0,
        "protein_g": 3.5,
        "carbs_g": 28.0,
        "fat_g": 9.0,
        "fiber_g": 3.0,
        "category": "condiment",
        "source": "tkpi_supplement",
        "food_name_lower": "bawang goreng",
        "food_name_en_lower": "fried shallots (bawang goreng)",
        "search_tokens": [
            "bawang", "goreng", "fried", "shallot", "onion", "shallots",
            "bawang goreng", "fried shallots", "fried onion",
        ],
    },
    {
        "id": "tkpi_NEW_022",
        "food_name": "Kecap Manis",
        "food_name_en": "Sweet Soy Sauce (Kecap Manis)",
        "calories_kcal": 200.0,
        "protein_g": 2.0,
        "carbs_g": 46.0,
        "fat_g": 0.0,
        "fiber_g": 0.0,
        "category": "sauce",
        "source": "tkpi_supplement",
        "food_name_lower": "kecap manis",
        "food_name_en_lower": "sweet soy sauce (kecap manis)",
        "search_tokens": [
            "kecap", "manis", "sweet", "soy", "sauce", "kecap manis",
            "sweet soy sauce", "indonesian", "soy_sauce", "dark soy",
        ],
    },
    {
        "id": "tkpi_NEW_023",
        "food_name": "Ketupat",
        "food_name_en": "Rice Cake / Ketupat",
        "calories_kcal": 130.0,
        "protein_g": 2.5,
        "carbs_g": 28.0,
        "fat_g": 0.3,
        "fiber_g": 1.5,
        "category": "staple",
        "source": "tkpi_supplement",
        "food_name_lower": "ketupat",
        "food_name_en_lower": "rice cake / ketupat",
        "search_tokens": [
            "ketupat", "rice", "cake", "compressed", "nasi", "lontong",
            "nasi impit", "rice cake", "lontong", "lontong", "rice_cake",
        ],
    },
]

# ── USDA entries to fix: remove Indonesian food words from search_tokens ─────

# These entries had Indonesian food tokens (bumbu, sambal, kecap, etc.)
# that caused them to match Indonesian dish names incorrectly.
USDA_TOKENS_TO_REMOVE = {
    "tomato_sauce_tomatoes,_tomato": [
        "bumbu", "sambal", "kecap", "kecap_manis", "kecap_asin",
        "sambal_kacang", "bumbu_kacang", "peanut_sauce",
    ],
    "beef": [
        "rendang", "gulai", "kari", "soto", "soto_ayam", "semur",
    ],
}

# ── Entries to delete from DB (bad data that causes mis-matches) ─────────────

DELETE_IDS = []  # None for now — we'll patch instead of delete


def add_missing_foods(project_id: str):
    """Add the 4 missing food entries to Firestore."""
    db = firestore.Client(project=project_id, database=project_id)
    coll = coll = db.collection("foods")

    for food in NEW_FOODS:
        doc_id = food["id"]
        doc_ref = coll.document(doc_id)
        # Read back existing doc to check if it already has clean search_tokens
        existing = doc_ref.get()
        if existing.exists:
            existing_tokens = existing.to_dict().get("search_tokens", [])
            if existing_tokens and existing_tokens != [doc_id]:  # already has real tokens
                print(f"  SKIP {doc_id}: already exists with tokens — not overwriting")
                continue
        doc_ref.set(food)
        print(f"  ADDED: {doc_id} — {food['food_name']} ({food['calories_kcal']} kcal)")


def sanitize_usda_tokens(project_id: str):
    """Remove Indonesian food words from USDA entries that are causing mis-matches."""
    db = firestore.Client(project=project_id, database=project_id)
    coll = db.collection("foods")

    for doc_id, tokens_to_remove in USDA_TOKENS_TO_REMOVE.items():
        doc_ref = coll.document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            print(f"  SKIP {doc_id}: not found in DB")
            continue

        data = doc.to_dict()
        existing_tokens = data.get("search_tokens", [])
        if not existing_tokens:
            print(f"  SKIP {doc_id}: has no search_tokens field")
            continue

        original_count = len(existing_tokens)
        cleaned = [t for t in existing_tokens if t not in tokens_to_remove]
        removed = [t for t in existing_tokens if t in tokens_to_remove]

        if removed:
            doc_ref.update({"search_tokens": cleaned})
            print(f"  FIXED {doc_id}: removed {removed}")
            print(f"    Tokens: {original_count} → {len(cleaned)}")
        else:
            print(f"  OK {doc_id}: no bad tokens found ({len(existing_tokens)} tokens)")


def delete_bad_entries(project_id: str):
    """Delete specific entries that are causing irreconcilable mis-matches."""
    if not DELETE_IDS:
        print("  No entries to delete (DELETE_IDS is empty)")
        return
    db = firestore.Client(project=project_id, database=project_id)
    for doc_id in DELETE_IDS:
        doc_ref = db.collection("foods").document(doc_id)
        doc_ref.delete()
        print(f"  DELETED: {doc_id}")


def main():
    parser = argparse.ArgumentParser(description="Patch missing foods + sanitize DB tokens")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    args = parser.parse_args()

    print("\n=== Adding missing food entries ===")
    add_missing_foods(args.project)

    print("\n=== Sanitizing USDA search_tokens ===")
    sanitize_usda_tokens(args.project)

    print("\n=== Done ===\n")


if __name__ == "__main__":
    exit(main())
