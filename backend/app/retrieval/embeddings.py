"""Modular Embedding Provider Interface with Bounded Caching & Dimension Validation (Phase 29)."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import threading
from typing import Protocol

from app.semantic.embedding import LocalEmbeddingService, embedding_service as default_local_embedder


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_query(self, query: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class CachedLocalEmbeddingProvider:
    """Wraps LocalEmbeddingService with bounded LRU cache, dimension validation, and retry."""

    def __init__(
        self,
        base_service: LocalEmbeddingService | None = None,
        max_cache_size: int = 1024,
        max_retries: int = 1,
    ) -> None:
        self.base = base_service or default_local_embedder
        self.model_name = self.base.model_name
        self.dimension = self.base.dimension
        self.max_cache_size = max(16, max_cache_size)
        self.max_retries = max(0, max_retries)
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_name}|{text}".encode("utf-8", errors="replace")).hexdigest()

    def _validate_dim(self, vec: list[float]) -> list[float]:
        if len(vec) != self.dimension:
            raise ValueError(f"Embedding dimension mismatch: expected {self.dimension}, got {len(vec)}.")
        return vec

    def embed_query(self, query: str) -> list[float]:
        res = self.embed_batch([query])
        return res[0] if res else [0.0] * self.dimension

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        outputs: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []

        with self._lock:
            for idx, txt in enumerate(texts):
                k = self._cache_key(txt)
                if k in self._cache:
                    self._cache.move_to_end(k)
                    outputs[idx] = self._cache[k]
                    self.cache_hits += 1
                else:
                    missing_indices.append(idx)
                    missing_texts.append(txt)
                    self.cache_misses += 1

        if missing_texts:
            vecs: list[list[float]] | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    vecs = self.base.embed_texts(missing_texts)
                    break
                except Exception:
                    if attempt >= self.max_retries:
                        raise
            assert vecs is not None
            with self._lock:
                for idx, txt, vec in zip(missing_indices, missing_texts, vecs):
                    valid = self._validate_dim(vec)
                    k = self._cache_key(txt)
                    self._cache[k] = valid
                    self._cache.move_to_end(k)
                    if len(self._cache) > self.max_cache_size:
                        self._cache.popitem(last=False)
                    outputs[idx] = valid

        return [v if v is not None else [0.0] * self.dimension for v in outputs]

    def stats(self) -> dict[str, int | str]:
        with self._lock:
            return {
                "model_name": self.model_name,
                "dimension": self.dimension,
                "cache_size": len(self._cache),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
            }


cached_embedding_provider = CachedLocalEmbeddingProvider()
