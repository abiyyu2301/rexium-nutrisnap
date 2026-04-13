"""
backend/nutrition.py — Firestore Nutrition DB with fuzzy search
Loads from Firestore 'foods' collection.
"""
import os
import json
from pathlib import Path
from typing import Optional

from google.cloud import firestore  # Google Cloud Firestore client

GCP_PROJECT = os.getenv("GCP_PROJECT", os.getenv("GCP_PROJECT_ID", ""))

# Local fallback data path (for local dev without GCP credentials)
LOCAL_DATA_PATH = Path(__file__).parent.parent / "nutrition-data" / "tkpi_clean.json"


class NutritionDB:
    """
    Fuzzy-match food names against the nutrition database.
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
                self._client = firestore.Client(project=self.project_id)
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
                    min(prev[j + 1] + 1,
                        curr[j] + 1,
                        prev[j] + (c1 != c2))
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
            # substring match — high score
            return 0.85 + 0.1 * (min(len(q), len(c)) / max(len(q), len(c)))
        # Levenshtein normalized
        dist = self._levenshtein(q, c)
        max_len = max(len(q), len(c))
        return max(0.0, 1.0 - (dist / max_len))

    def search_foods(self, query: str, limit: int = 5) -> list[dict]:
        """
        Fuzzy search foods by name.
        Tries Firestore first, falls back to local JSON.
        Returns top `limit` matches sorted by score descending.
        """
        if not query or len(query) < 2:
            return []

        results = []

        # Try Firestore
        if self.client:
            try:
                coll = self.client.collection("foods")
                # Simple prefix match on food_name
                docs = (
                    coll.where("food_name_lower", ">=", query.lower())
                        .where("food_name_lower", "<=", query.lower() + "\uf8ff")
                        .limit(limit * 2)
                        .stream()
                )
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = doc.id
                    results.append(d)
            except Exception:
                pass  # Fall back to local

        # Local fallback
        if not results:
            all_foods = self._load_local()
            for food in all_foods:
                name = food.get("food_name", "")
                score = self._score(query, name)
                if score > 0.4:
                    results.append(food | {"score": score, "id": food.get("id", "")})

        # Fuzzy sort on local results
        if results and "score" not in results[0]:
            scored = [
                (f, self._score(query, f.get("food_name", "")))
                for f in results
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            results = [f[0] for f in scored[:limit]]

        # Add score if missing
        for r in results:
            if "score" not in r:
                r["score"] = self._score(query, r.get("food_name", ""))

        return results[:limit]
