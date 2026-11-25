"""Local embedding service supporting Sentence Transformers and resilient fallback."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger("semantic.embedding")


class LocalEmbeddingService:
    """Manages embedding generation with lazy model loading and deterministic fallback."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        dimension: int = 384,
        batch_size: int = 16,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = batch_size
        self._model: Any = None
        self._is_loaded: bool = False
        self._backend: str = "uninitialized"
        self._load_error: str | None = None

    def _ensure_model(self) -> None:
        """Lazily initialize the local embedding model."""
        if self._is_loaded:
            return

        import os

        enable_native = os.getenv("LUMO_ENABLE_NATIVE_EMBEDDINGS", "false").lower() in {"1", "true", "yes"}
        if not enable_native:
            self._backend = "semantic-projection"
            self._is_loaded = True
            logger.info(
                "Semantic embedding initialized with pure-Python vector projection "
                "(Set LUMO_ENABLE_NATIVE_EMBEDDINGS=true in .env to enable native SentenceTransformers)."
            )
            return

        try:
            logger.info("Attempting to load local SentenceTransformer: %s", self.model_name)
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._backend = "sentence-transformers"
            self._is_loaded = True
            logger.info("Successfully loaded SentenceTransformer: %s", self.model_name)
        except (ImportError, OSError, Exception) as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"
            self._backend = "semantic-projection"
            self._is_loaded = True
            logger.info("Native embedding model unavailable (%s). Falling back to vector projection.", self._load_error)

    def embed_query(self, query: str) -> list[float]:
        """Generate a single normalized embedding vector for a search query."""
        clean = (query or "").strip()
        if not clean:
            return [0.0] * self.dimension

        results = self.embed_texts([clean])
        return results[0] if results else [0.0] * self.dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized embedding vectors for a list of text strings."""
        if not texts:
            return []

        self._ensure_model()

        if self._model is not None and self._backend == "sentence-transformers":
            try:
                embeddings = self._model.encode(
                    texts,
                    batch_size=self.batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                return [vec.tolist() for vec in embeddings]
            except Exception as exc:
                logger.error("SentenceTransformer inference failed: %s", exc)

        # Resilient fallback: generates deterministic unit-normalized 384-d vectors
        return [self._generate_fallback_vector(t) for t in texts]

    def _generate_fallback_vector(self, text: str) -> list[float]:
        """Generate a deterministic 384-dimensional unit vector using n-gram token hashing."""
        vector = [0.0] * self.dimension
        tokens = [t.lower() for t in re.findall(r"\w+", text) if len(t) > 1]
        if not tokens:
            tokens = ["empty"]

        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vector[idx] += sign

        # Unit normalize (L2 norm)
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0.0:
            return [v / norm for v in vector]
        return [1.0 / math.sqrt(self.dimension)] * self.dimension

    def get_status(self) -> dict[str, Any]:
        """Return operational diagnostics for the embedding subsystem."""
        self._ensure_model()
        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "backend": self._backend,
            "is_native_loaded": self._model is not None,
            "load_error": self._load_error,
        }


# Singleton service instance
embedding_service = LocalEmbeddingService()
