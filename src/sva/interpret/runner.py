"""Interpret runner — takes any Interpreter, produces canonical Event rows."""

from __future__ import annotations

from sva.models import Event, MemoryRecord, Observation
from sva.observability import TraceContext
from sva.interpret.adapters.base import Interpreter
from sva.interpret.adapters.claude import ClaudeInterpreter


def make_default_interpreter() -> Interpreter:
    """Single import-swap point for switching the default LLM backend."""
    return ClaudeInterpreter()


def run_point(
    ctx: TraceContext,
    observations: list[Observation],
    interpreter: Interpreter | None = None,
    retrieved: list[MemoryRecord] | None = None,
) -> list[Event]:
    i = interpreter or make_default_interpreter()
    return i.interpret(ctx, observations, retrieved or [])


__all__ = ["run_point", "make_default_interpreter"]
