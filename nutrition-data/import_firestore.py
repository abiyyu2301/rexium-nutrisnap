"""
nutrition-data/import_firestore.py
Idempotent Firestore seed — writes all foods from tkpi_clean.json to Firestore.
Run: python3 import_firestore.py --project rexium-nutrisnap
"""
import argparse
import json
import time
from pathlib import Path

from google.cloud import firestore
from google.auth import default


def load_foods(data_path: str = None) -> list[dict]:
    """Load food data from local JSON files."""
    if data_path:
        path = Path(data_path)
    else:
        base = Path(__file__).parent
        path = base / ".." / "tkpi-scraper" / "data" / "cleaned" / "tkpi_clean.json"
    foods = []
    if path.exists():
        with open(path) as f:
            foods = json.load(f)
    print(f"Loaded {len(foods)} foods from JSON ({path})")
    return foods


def import_foods(project_id: str, foods: list[dict]):
    """Write foods to Firestore foods collection."""
    print(f"Connecting to Firestore project: {project_id}")
    db = firestore.Client(project=project_id, database=project_id)
    coll = db.collection("foods")

    batch_size = 50
    for i in range(0, len(foods), batch_size):
        batch = db.batch()
        chunk = foods[i:i + batch_size]

        for food in chunk:
            doc_id = food.get("id", food.get("food_name", "").lower().replace(" ", "_"))
            doc_ref = coll.document(doc_id)

            # Add lowercase searchable field for prefix queries
            doc_data = dict(food)
            doc_data["food_name_lower"] = food.get("food_name", "").lower()
            if "food_name_en" in food:
                doc_data["food_name_en_lower"] = food["food_name_en"].lower()

            batch.set(doc_ref, doc_data)

        batch.commit()
        print(f"  Committed batch {i // batch_size + 1} ({len(chunk)} docs)")

    print(f"\nImport complete: {len(foods)} foods → Firestore")


def main():
    parser = argparse.ArgumentParser(description="Seed Firestore with nutrition data")
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--data", help="Path to tkpi_clean.json (default: auto-detect)")
    args = parser.parse_args()

    # Auto-detect credentials
    try:
        credentials, _ = default()
    except Exception:
        print("WARNING: No GCP credentials found. Run: gcloud auth application-default login")
        credentials = None

    foods = load_foods(args.data)
    if not foods:
        print("ERROR: No food data found")
        return 1

    import_foods(args.project, foods)
    return 0


if __name__ == "__main__":
    exit(main())
