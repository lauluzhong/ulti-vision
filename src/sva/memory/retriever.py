"""Memory retriever — Phase 1 zero-retrieval stub (CONTEXT D-08).

Phase 5 replaces the retrieve() body with pgvector + tag-filter logic. The signature here
is final; any change to it is a Phase 1 regression.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sva.memory.records_dao import list_memory_records
from sva.models import MemoryRecord


class RetrievalQuery(BaseModel):
    """Swap-safe retrieval input. Phase 5 extends behaviour only; shape stays fixed."""

    model_config = ConfigDict(extra="forbid")
    event_candidate_type: str
    context_text: str = ""
    current_coach_id: str | None = None
    budget: int = Field(ge=1, le=20, default=6)


class MemoryRetriever:
    """Phase 5: scope-aware tag-first retrieval with honest non-vector fallback."""

    async def retrieve(
        self,
        query: RetrievalQuery,
        tags: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        """Return relevant memory records within the fixed swap-safe contract."""
        effective_limit = limit or query.budget
        scope_order = (
            [f"coach:{query.current_coach_id}", "global"]
            if query.current_coach_id
            else ["global"]
        )
        candidate_tags: list[str] = []
        for value in [query.event_candidate_type, *(tags or [])]:
            normalized = value.strip()
            if normalized and normalized not in candidate_tags:
                candidate_tags.append(normalized)
        if not candidate_tags:
            return []

        seen: set[str] = set()
        ordered: list[MemoryRecord] = []
        for scope in scope_order:
            for tag in candidate_tags:
                for record in list_memory_records(scopes=[scope], tag=tag, limit=effective_limit):
                    if record.memory_id in seen:
                        continue
                    seen.add(record.memory_id)
                    ordered.append(record)
                    if len(ordered) >= effective_limit:
                        return ordered
        return ordered


__all__ = ["MemoryRetriever", "RetrievalQuery"]
