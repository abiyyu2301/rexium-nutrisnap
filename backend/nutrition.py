"""
backend/nutrition.py — Firestore Nutrition DB with fuzzy search

Searches via:
1. array_contains on search_tokens (word-level partial match)
2. Firestore prefix match on food_name_lower (fallback)
3. Local JSON fallback (local dev without GCP credentials)
"""
import os
import json
import re
from pathlib import Path
from typing import Optional

from google.cloud import firestore

GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GCP_PROJECT_ID", ""))
LOCAL_DATA_PATH = Path(__file__).parent.parent / "nutrition-data" / "tkpi_clean.json"

# English -> Indonesian food term translations
EN_TO_ID = {
    "rice": {"nasi", "padi"},
    "noodle": {"mie", "mi"},
    "chicken": {"ayam"},
    "beef": {"sapi", "daging_sapi"},
    "pork": {"babi"},
    "fish": {"ikan"},
    "shrimp": {"udang"},
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
    "chili": {"cabai"},
    "pepper": {"merica"},
    "curry": {"kari", "gulai"},
    "soup": {"soto", "sup", "kuah"},
    "fried": {"goreng"},
    "grilled": {"panggang", "bakar"},
    "bread": {"roti"},
    "fruit": {"buah"},
    "coffee": {"kopi"},
    "tea": {"teh"},
    "milk": {"susu"},
    "coconut": {"kelapa", "santan"},
    "snack": {"kudapan", "cemilan"},
    "meal": {"makan"},
    "sauce": {"saus", "sambal"},
    "sweet": {"manis"},
    "spicy": {"pedas"},
}


class NutritionDB:
    """
    Fuzzy-match food names against the Firestore nutrition database.
    Falls back to local JSON when Firestore is unavailable (local dev).
    """

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or GCP_PROJECT
        self._client = None
        self._local_cache = None

    @property
    def client(self):
        if self._client is None and self.project_id:
            try:
                self._client = firestore.Client(
                    project=self.project_id,
                    database=self.project_id,
                )
            except Exception:
                self._client = None
        return self._client

    def _load_local(self) -> list[dict]:
        """Load from local JSON fallback."""
        if self._local_cache is not None:
            return self._local_cache
        if LOCAL_DATA_PATH.exists():
            with open(LOCAL_DATA_PATH) as f:
                self._local_cache = json.load(f)
        else:
            self._local_cache = []
        return self._local_cache

    def _expand_query(self, query: str) -> list[str]:
        """Expand a search query with translations and sub-queries."""
        q = query.lower().strip()
        queries = [q]

        # Add individual words
        words = re.findall(r"[a-z0-9]+", q)
        queries.extend(words)

        # Add translations
        for eng, indonesians in EN_TO_ID.items():
            if eng in q or any(w.startswith(eng) for w in words):
                queries.extend(indonesians)

        return list(dict.fromkeys(queries))  # dedupe

    def _levenshtein(self, s1: str, s2: str) -> int:
        """Simple edit distance."""
        if len(s1) < len(s2):
            return self._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                curr.append(
                    min(
                        prev[j + 1] + 1,
                        curr[j] + 1,
                        prev[j] + (c1 != c2),
                    )
                )
            prev = curr
        return prev[-1]

    def _score(self, query: str, candidate: str) -> float:
        """
        Score how well candidate matches query (0-1).
        Uses normalized Levenshtein + substring match.
        """
        q = query.lower().strip()
        c = candidate.lower().strip()
        if q == c:
            return 1.0
        if q in c or c in q:
            return 0.85 + 0.1 * (min(len(q), len(c)) / max(len(q), len(c)))
        dist = self._levenshtein(q, c)
        max_len = max(len(q), len(c))
        return max(0.0, 1.0 - (dist / max_len))

    def search_foods(self, query: str, limit: int = 5) -> list[dict]:
        """
        Fuzzy search foods by name.
        Tries:
          1. array_contains on search_tokens (word partial match)
          2. Prefix match on food_name_lower (fallback)
          3. Local JSON fallback (local dev)
        Returns top `limit` matches sorted by score descending.
        """
        if not query or len(query) < 2:
            return []

        results = []
        expanded = self._expand_query(query)
        seen_ids = set()

        # Strategy 1: array_contains with expanded query terms
        if self.client:
            try:
                coll = self.client.collection("foods")
                for term in expanded[:6]:  # limit OR clauses
                    docs = (
                        coll.where("search_tokens", "array_contains", term)
                            .limit(limit * 3)
                            .stream()
                    )
                    for doc in docs:
                        if doc.id in seen_ids:
                            continue
                        seen_ids.add(doc.id)
                        d = doc.to_dict()
                        d["id"] = doc.id
                        score = self._score(query, d.get("food_name", ""))
                        d["score"] = score
                        results.append(d)
            except Exception:
                pass  # fall through to next strategy

        # Strategy 2: prefix match on food_name_lower
        if not results and self.client:
            try:
                coll = self.client.collection("foods")
                for term in expanded[:3]:
                    docs = (
                        coll.where("food_name_lower", ">=", term)
                            .where("food_name_lower", "<=", term + "\uf8ff")
                            .limit(limit * 3)
                            .stream()
                    )
                    for doc in docs:
                        if doc.id in seen_ids:
                            continue
                        seen_ids.add(doc.id)
                        d = doc.to_dict()
                        d["id"] = doc.id
                        score = self._score(query, d.get("food_name", ""))
                        d["score"] = score
                        results.append(d)
            except Exception:
                pass

        # Strategy 3: local JSON fallback
        if not results:
            all_foods = self._load_local()
            for food in all_foods:
                name = food.get("food_name", "")
                score = self._score(query, name)
                if score > 0.4:
                    results.append(food | {"score": score, "id": food.get("id", "")})

        # Sort by score
        if results:
            results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return results[:limit]
