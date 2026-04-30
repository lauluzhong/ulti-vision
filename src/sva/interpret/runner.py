"""Interpret runner — takes any Interpreter, produces canonical Event rows."""

from __future__ import annotations

from sva.models import Event, MemoryRecord, Observation
from sva.observability import TraceContext
from sva.interpret.adapters.base import Interpreter
from sva.interpret.adapters.gemini import GeminiInterpreter


def make_default_interpreter() -> Interpreter:
    """Single import-swap point for switching the default LLM backend.

    v0: Gemini 2.5 Flash for both VLM (perceive) and LLM (interpret) — same key,
    same SDK, ~20x cheaper than Claude Sonnet for this commodity-LLM task.
    To swap: write a new adapter under sva/interpret/adapters/, change one line here.
    """
    return GeminiInterpreter()


def run_point(
    ctx: TraceContext,
    observations: list[Observation],
    interpreter: Interpreter | None = None,
    retrieved: list[MemoryRecord] | None = None,
) -> list[Event]:
    i = interpreter or make_default_interpreter()
    return i.interpret(ctx, observations, retrieved or [])


__all__ = ["run_point", "make_default_interpreter"]
