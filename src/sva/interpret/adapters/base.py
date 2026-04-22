"""Interpreter Protocol — swap-safe LLM interface (ARCHITECTURE.md Pattern 1)."""

from __future__ import annotations

from typing import Protocol

from sva.models import Event, MemoryRecord, Observation
from sva.observability import TraceContext


class Interpreter(Protocol):
    """LLM adapter contract. Implementations live under sva.interpret.adapters.*."""

    def interpret(
        self,
        ctx: TraceContext,
        observations: list[Observation],
        retrieved: list[MemoryRecord],
    ) -> Event: ...


__all__ = ["Interpreter"]
