"""Memory retriever with Phase 5 semantic ranking behind a swap-safe seam."""

from __future__ import annotations

from collections.abc import Mapping
import json

from pydantic import BaseModel, ConfigDict, Field

from sva.memory.embeddings import (
    EmbeddingProvider,
    content_hash,
    cosine_similarity,
    make_default_embedding_provider,
)
from sva.memory.records_dao import (
    list_memory_embeddings,
    list_memory_records,
    upsert_memory_embedding,
)
from sva.models import MemoryRecord


class RetrievalQuery(BaseModel):
    """Swap-safe retrieval input. Phase 5 extends behaviour only; shape stays fixed."""

    model_config = ConfigDict(extra="forbid")
    event_candidate_type: str
    context_text: str = ""
    current_coach_id: str | None = None
    budget: int = Field(ge=1, le=20, default=6)


class MemoryRetriever:
    """Phase 5: scope-aware tag-first retrieval with semantic ranking."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        candidate_multiplier: int = 3,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._candidate_multiplier = max(1, candidate_multiplier)

    async def retrieve(
        self,
        query: RetrievalQuery,
        tags: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        """Return relevant memory records within the fixed swap-safe contract."""
        effective_limit = limit or query.budget
        candidate_tags = _candidate_tags(query.event_candidate_type, tags)
        if not candidate_tags or effective_limit <= 0:
            return []
        candidate_limit = max(effective_limit, effective_limit * self._candidate_multiplier)
        scope_order = (
            [f"coach:{query.current_coach_id}", "global"] if query.current_coach_id else ["global"]
        )

        seen: set[str] = set()
        ordered_candidates: list[MemoryRecord] = []
        for scope in scope_order:
            for tag in candidate_tags:
                for record in list_memory_records(scopes=[scope], tag=tag, limit=candidate_limit):
                    if record.memory_id in seen:
                        continue
                    seen.add(record.memory_id)
                    ordered_candidates.append(record)
        if not ordered_candidates:
            return []

        ranked = self._rank_semantically(query, ordered_candidates)
        return ranked[:effective_limit]

    def _rank_semantically(
        self,
        query: RetrievalQuery,
        candidates: list[MemoryRecord],
    ) -> list[MemoryRecord]:
        provider = self._embedding_provider or _safe_default_provider()
        if provider is None:
            return candidates

        try:
            query_vector = provider.embed_query(_semantic_query_text(query))
            stored = list_memory_embeddings(
                memory_ids=[record.memory_id for record in candidates],
                provider=provider.provider_name,
                model_id=provider.model_id,
            )
            missing_records: list[MemoryRecord] = []
            vectors: dict[str, list[float]] = {}
            for record in candidates:
                record_text = _memory_text(record)
                current_hash = content_hash(record_text)
                stored_row = stored.get(record.memory_id)
                stored_hash = _embedding_content_hash(stored_row)
                stored_vector = _embedding_vector(stored_row)
                if stored_hash == current_hash and stored_vector:
                    vectors[record.memory_id] = stored_vector
                    continue
                missing_records.append(record)

            if missing_records:
                document_vectors = provider.embed_documents([_memory_text(record) for record in missing_records])
                for record, vector in zip(missing_records, document_vectors, strict=False):
                    normalized = list(vector)
                    vectors[record.memory_id] = normalized
                    upsert_memory_embedding(
                        memory_id=record.memory_id,
                        provider=provider.provider_name,
                        model_id=provider.model_id,
                        content_hash=content_hash(_memory_text(record)),
                        vector=normalized,
                    )

            scored = sorted(
                enumerate(candidates),
                key=lambda item: (
                    -cosine_similarity(query_vector, vectors.get(item[1].memory_id, [])),
                    _scope_tiebreak(item[1].scope),
                    item[0],
                ),
            )
            return [record for _, record in scored]
        except Exception:
            return candidates


def _safe_default_provider() -> EmbeddingProvider | None:
    try:
        return make_default_embedding_provider()
    except Exception:
        return None


def _candidate_tags(event_candidate_type: str, tags: list[str] | None) -> list[str]:
    candidate_tags: list[str] = []
    for value in [event_candidate_type, *(tags or [])]:
        normalized = value.strip()
        if normalized and normalized not in candidate_tags:
            candidate_tags.append(normalized)
    return candidate_tags


def _semantic_query_text(query: RetrievalQuery) -> str:
    parts = [
        f"event_candidate_type: {query.event_candidate_type.strip()}",
        f"context: {query.context_text.strip()}",
    ]
    if query.current_coach_id:
        parts.append(f"coach_scope: {query.current_coach_id}")
    return "\n".join(part for part in parts if not part.endswith(": "))


def _memory_text(record: MemoryRecord) -> str:
    if record.embedding_input.strip():
        return record.embedding_input.strip()
    payload_text = json.dumps(record.payload, sort_keys=True, separators=(",", ":"))
    tags_text = ", ".join(record.tags)
    return (
        f"kind: {record.kind}\n"
        f"scope: {record.scope}\n"
        f"tags: {tags_text}\n"
        f"payload: {payload_text}"
    )


def _scope_tiebreak(scope: str) -> int:
    return 0 if scope.startswith("coach:") else 1


def _embedding_content_hash(stored_row: object | None) -> str | None:
    if stored_row is None:
        return None
    if isinstance(stored_row, Mapping):
        value = stored_row.get("content_hash")
        return str(value) if value is not None else None
    value = getattr(stored_row, "content_hash", None)
    return str(value) if value is not None else None


def _embedding_vector(stored_row: object | None) -> list[float]:
    if stored_row is None:
        return []
    raw = None
    if isinstance(stored_row, Mapping):
        raw = stored_row.get("vector")
    else:
        raw = getattr(stored_row, "vector", None)
    if not raw:
        return []
    return [float(value) for value in raw]


__all__ = ["MemoryRetriever", "RetrievalQuery"]
