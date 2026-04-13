"""
nutrition-data/add_search_tokens.py
Batch migration: adds `search_tokens` array field to all foods in Firestore.
Uses food_name as matching key since JSON IDs != Firestore doc IDs.
"""
import re

from google.cloud import firestore
from google.oauth2 import service_account

GCP_PROJECT = "rexium-nutrisnap"
DATA_PATH = "/Users/rex/tkpi-scraper/data/cleaned/tkpi_clean.json"


def tokenize(text: str) -> list[str]:
    """Extract searchable tokens from a food name."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    words = [w for w in words if len(w) > 1]
    return list(dict.fromkeys(words))


# English -> Indonesian food term translations
# When user searches for an English term, we also search Indonesian equivalents
EN_TO_ID = {
    "rice": {"nasi", "padi"},
    "noodle": {"mie", "mi", "mie"},
    "chicken": {"ayam", "daging_ayam"},
    "beef": {"sapi", "daging_sapi", "daging"},
    "pork": {"babi", "daging_babi"},
    "fish": {"ikan"},
    "shrimp": {"udang", "prawn"},
    "tofu": {"tahu"},
    "tempeh": {"tempe"},
    "egg": {"telur"},
    "vegetable": {"sayur", "sayuran"},
    "cabbage": {"kubis", "kol"},
    "spinach": {"bayam"},
    "kale": {"kangkung"},
    "broccoli": {"brokoli"},
    "carrot": {"wortel"},
    "cucumber": {"mentimun"},
    "tomato": {"tomat"},
    "onion": {"bawang"},
    "garlic": {"bawang_putih"},
    "chili": {"cabai", "cabay"},
    "pepper": {"merica", "lada"},
    "curry": {"kari", "gulai", "santan"},
    "soup": {"soto", "sup", "kuah", "sop"},
    "fried": {"goreng"},
    "grilled": {"panggang", "bakar"},
    "steamed": {"kukus", "rebus"},
    "roasted": {"panggang"},
    "bread": {"roti"},
    "fruit": {"buah"},
    "coffee": {"kopi"},
    "tea": {"teh"},
    "milk": {"susu"},
    "coconut": {"kelapa", "santan"},
    "rice cake": {"lontong", "ketupat"},
    "cake": {"kue", "bolu"},
    "snack": {"kudapan", "cemilan", "jajanan"},
    "breakfast": {"sarapan"},
    "meal": {"makan"},
    "sauce": {"saus", "sambal", "bumbu"},
    "sweet": {"manis"},
    "salty": {"asin"},
    "sour": {"asam"},
    "spicy": {"pedas"},
}


def main():
    import json
    with open(DATA_PATH) as f:
        foods = json.load(f)
    print(f"Loaded {len(foods)} foods from JSON")

    credentials = service_account.Credentials.from_service_account_file(
        "/Users/rex/.config/gcloud/sa-key.json",
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    db = firestore.Client(project=GCP_PROJECT, database=GCP_PROJECT, credentials=credentials)
    coll = db.collection("foods")

    # Build a name->doc_ref map from existing Firestore docs
    print("Building name index from Firestore...")
    existing = {}
    for doc in coll.limit(2000).stream():
        d = doc.to_dict()
        fname = d.get("food_name", "").lower()
        if fname:
            existing[fname] = doc.id

    print(f"Found {len(existing)} existing docs in Firestore")

    # Also build from food_name_en
    for doc in coll.limit(2000).stream():
        d = doc.to_dict()
        fname_en = d.get("food_name_en", "").lower()
        if fname_en and fname_en not in existing:
            existing[fname_en] = doc.id

    batch_size = 50
    updated = 0
    errors = 0

    for i in range(0, len(foods), batch_size):
        batch = db.batch()
        chunk = foods[i:i + batch_size]

        for food in chunk:
            fname = food.get("food_name", "").lower()
            fname_en = food.get("food_name_en", "").lower()

            # Find matching Firestore doc
            doc_id = existing.get(fname) or existing.get(fname_en)

            if not doc_id:
                # Try partial match
                for key, vid in existing.items():
                    if fname in key or key in fname:
                        doc_id = vid
                        break

            if not doc_id:
                # Skip - doc doesn't exist in Firestore
                continue

            doc_ref = coll.document(doc_id)

            # Build search tokens
            tokens = set(tokenize(fname))
            tokens.update(tokenize(fname_en))

            # Add translations
            for eng, indonesians in EN_TO_ID.items():
                if eng in tokens or any(t.startswith(eng) or eng.startswith(t) for t in tokens):
                    tokens.update(indonesians)

            batch.update(doc_ref, {"search_tokens": list(tokens)})
            updated += 1

        try:
            batch.commit()
            print(f"  Batch {i // batch_size + 1}: {updated} updated")
        except Exception as e:
            errors += 1
            print(f"  Batch {i // batch_size + 1} ERROR: {e}")

    print(f"\nDone: {updated} documents updated, {errors} batch errors")


if __name__ == "__main__":
    main()
