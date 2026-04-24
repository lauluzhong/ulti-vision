"""Embedding helpers for Phase 5 semantic memory ranking."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

try:
    from google import genai
except ImportError:  # pragma: no cover - missing dependency in some dev envs
    genai = None  # type: ignore[assignment]

from sva.config import settings

_DEFAULT_MODEL_ID = "gemini-embedding-2"
_DEFAULT_OUTPUT_DIMENSIONALITY = 768


def content_hash(text: str) -> str:
    """Return a stable hash for embedding freshness checks."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def normalize_vector(values: list[float]) -> list[float]:
    """Normalize vectors so cosine ranking is stable across providers."""
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        return list(values)
    return [value / magnitude for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for same-length vectors."""
    if not left or not right or len(left) != len(right):
        return -1.0
    return sum(lhs * rhs for lhs, rhs in zip(left, right, strict=False))


class EmbeddingProvider(Protocol):
    """Provider-neutral seam for query/document ranking embeddings."""

    provider_name: str
    model_id: str
    output_dimensionality: int

    def embed_query(self, text: str) -> list[float]:
        """Embed a retrieval query."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed candidate documents in retrieval space."""


class GeminiEmbeddingProvider:
    """Gemini text embedder using the current stable embedding model."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        model_id: str = _DEFAULT_MODEL_ID,
        output_dimensionality: int = _DEFAULT_OUTPUT_DIMENSIONALITY,
    ) -> None:
        self.model_id = model_id
        self.output_dimensionality = output_dimensionality

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(f"Retrieval query:\n{text.strip()}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(f"Retrieval document:\n{text.strip()}") for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        if genai is None:
            raise RuntimeError("google-genai is not installed")
        client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
        response = client.models.embed_content(
            model=self.model_id,
            contents=text,
            config=genai.types.EmbedContentConfig(
                output_dimensionality=self.output_dimensionality,
            ),
        )
        embeddings = getattr(response, "embeddings", None) or []
        if not embeddings:
            raise ValueError("Gemini embedding response did not include embeddings")
        values = list(getattr(embeddings[0], "values", None) or [])
        if not values:
            raise ValueError("Gemini embedding response did not include vector values")
        return normalize_vector([float(value) for value in values])


def make_default_embedding_provider() -> EmbeddingProvider:
    """Return the repo's default semantic-ranking provider."""
    return GeminiEmbeddingProvider()


__all__ = [
    "EmbeddingProvider",
    "GeminiEmbeddingProvider",
    "content_hash",
    "cosine_similarity",
    "make_default_embedding_provider",
    "normalize_vector",
]
