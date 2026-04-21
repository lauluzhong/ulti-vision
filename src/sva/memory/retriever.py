"""Memory retriever — Phase 1 zero-retrieval stub (CONTEXT D-08).

Phase 5 replaces the retrieve() body with pgvector + tag-filter logic. The signature here
is final; any change to it is a Phase 1 regression.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sva.models import MemoryRecord


class RetrievalQuery(BaseModel):
    """Swap-safe retrieval input. Phase 5 extends behaviour only; shape stays fixed."""

    model_config = ConfigDict(extra="forbid")
    event_candidate_type: str
    context_text: str = ""
    current_coach_id: str | None = None
    budget: int = Field(ge=1, le=20, default=6)


class MemoryRetriever:
    """Phase 1: always returns []. Phase 5: tag-filter → vector-rank → diversity-cap."""

    async def retrieve(
        self,
        query: RetrievalQuery,
        tags: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        """Return relevant memory records. Phase 1 stub: always []."""
        _ = query, tags, limit  # Phase 5 will use these.
        return []


__all__ = ["MemoryRetriever", "RetrievalQuery"]
