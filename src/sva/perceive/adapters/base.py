"""Perceiver Protocol — swap-safe VLM interface (ARCHITECTURE.md Pattern 1)."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from sva.models import MemoryRecord, Observation
from sva.observability import TraceContext


class PerceiveWindow(BaseModel):
    """Input to Perceiver.perceive — one sampled window ready for VLM evaluation."""

    model_config = ConfigDict(extra="forbid")
    window_id: str
    video_id: str
    video_ts_start_ms: int = Field(ge=0)
    video_ts_end_ms: int = Field(ge=0)
    transcoded_path: str


class Perceiver(Protocol):
    """VLM adapter contract. Implementations live under sva.perceive.adapters.*.

    `retrieved` is optional perceive-relevant memory (Phase 5+). Adapters that
    don't yet wire memory in (test stubs, legacy implementations) may ignore it.
    """

    def perceive(
        self,
        ctx: TraceContext,
        window: PerceiveWindow,
        retrieved: list[MemoryRecord] | None = None,
    ) -> Observation: ...


__all__ = ["Perceiver", "PerceiveWindow"]
