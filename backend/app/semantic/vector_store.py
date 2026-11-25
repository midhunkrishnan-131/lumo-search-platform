"""Qdrant REST client and persistent vector storage for LUMO Phase 6."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger("semantic.vector_store")


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two unit-normalized vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return max(0.0, min(1.0, dot))


class QdrantVectorStore:
    """Qdrant REST API client with local JSON-file persistence fallback."""

    def __init__(
        self,
        base_url: str = "http://localhost:6333",
        collection_name: str = "lumo_documents",
        storage_path: str = "./qdrant_storage",
        dimension: int = 384,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection_name = collection_name
        self.storage_dir = Path(storage_path)
        self.storage_file = self.storage_dir / f"{collection_name}_fallback.json"
        self.dimension = dimension
        self.timeout = timeout
        self._local_points: dict[str, dict[str, Any]] = {}
        self._ensure_storage_dir()
        self._load_local_fallback()

    def _ensure_storage_dir(self) -> None:
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create vector storage directory: %s", exc)

    def _load_local_fallback(self) -> None:
        """Load fallback points from disk if file exists."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self._local_points = json.load(f)
            except Exception as exc:
                logger.warning("Error reading local vector fallback store: %s", exc)
                self._local_points = {}

    def _save_local_fallback(self) -> None:
        """Save fallback points to disk."""
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self._local_points, f)
        except Exception as exc:
            logger.warning("Error persisting local vector fallback store: %s", exc)

    def is_qdrant_available(self) -> bool:
        """Ping local Qdrant server health."""
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.base_url}/collections")
                return resp.status_code == 200
        except Exception:
            return False

    def ensure_collection(self) -> bool:
        """Ensure target collection exists on Qdrant server or fallback."""
        if not self.is_qdrant_available():
            logger.info("Qdrant server not reached. Operating in local persistent fallback mode.")
            return True

        try:
            with httpx.Client(timeout=self.timeout) as client:
                check_resp = client.get(f"{self.base_url}/collections/{self.collection_name}")
                if check_resp.status_code == 200:
                    return True

                # Create collection
                payload = {
                    "vectors": {
                        "size": self.dimension,
                        "distance": "Cosine",
                    }
                }
                put_resp = client.put(
                    f"{self.base_url}/collections/{self.collection_name}",
                    json=payload,
                )
                return put_resp.status_code in {200, 201}
        except Exception as exc:
            logger.warning("Error configuring Qdrant collection: %s", exc)
            return False

    def upsert_points(self, points: list[dict[str, Any]]) -> bool:
        """Upsert vector points into Qdrant or fallback store.

        Each point must contain: id, vector, payload.
        """
        if not points:
            return True

        # Always update local store to preserve persistence
        for pt in points:
            pid = str(pt["id"])
            self._local_points[pid] = pt
        self._save_local_fallback()

        if not self.is_qdrant_available():
            return True

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.put(
                    f"{self.base_url}/collections/{self.collection_name}/points",
                    json={"points": points},
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Qdrant upsert failed (%s). Points safely saved in fallback store.", exc)
            return True

    def search_vectors(
        self,
        query_vector: list[float],
        limit: int = 20,
        domain_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search nearest vector points."""
        if self.is_qdrant_available():
            try:
                body: dict[str, Any] = {
                    "vector": query_vector,
                    "limit": limit,
                    "with_payload": True,
                }
                if domain_filter:
                    body["filter"] = {
                        "must": [
                            {"key": "domain", "match": {"value": domain_filter.lower()}}
                        ]
                    }

                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/collections/{self.collection_name}/points/search",
                        json=body,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("result", [])
            except Exception as exc:
                logger.warning("Qdrant search error (%s). Falling back to local vector store.", exc)

        # Local cosine similarity search
        candidates: list[dict[str, Any]] = []
        for pid, pt in self._local_points.items():
            payload = pt.get("payload", {})
            if domain_filter and payload.get("domain", "").lower() != domain_filter.lower():
                continue

            vec = pt.get("vector", [])
            score = cosine_similarity(query_vector, vec)
            candidates.append({
                "id": pid,
                "score": score,
                "payload": payload,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]

    def delete_document_vectors(self, document_id: str) -> bool:
        """Delete all chunk vectors associated with a document ID."""
        # 1. Remove from local store
        to_del = [
            pid for pid, pt in self._local_points.items()
            if pt.get("payload", {}).get("document_id") == document_id
        ]
        for pid in to_del:
            self._local_points.pop(pid, None)
        self._save_local_fallback()

        if not self.is_qdrant_available():
            return True

        # 2. Remove from Qdrant via filter
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/collections/{self.collection_name}/points/delete",
                    json={
                        "filter": {
                            "must": [
                                {"key": "document_id", "match": {"value": document_id}}
                            ]
                        }
                    },
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Qdrant delete error: %s", exc)
            return True

    def count_vectors(self) -> int:
        """Return total stored vectors count."""
        if self.is_qdrant_available():
            try:
                with httpx.Client(timeout=2.0) as client:
                    resp = client.get(f"{self.base_url}/collections/{self.collection_name}")
                    if resp.status_code == 200:
                        return resp.json().get("result", {}).get("points_count", len(self._local_points))
            except Exception:
                pass
        return len(self._local_points)


# Default vector store singleton
vector_store = QdrantVectorStore()
