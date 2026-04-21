"""Perceive runner — takes any Perceiver, runs it against a window, returns an Observation."""

from __future__ import annotations

from sva.models import Observation
from sva.observability import TraceContext
from sva.perceive.adapters.base import Perceiver, PerceiveWindow
from sva.perceive.adapters.gemini import GeminiPerceiver


def make_default_perceiver() -> Perceiver:
    """Single import-swap point for switching the default VLM backend (D-03).

    Changing the VLM backend ONLY requires editing this function's return statement.
    """
    return GeminiPerceiver()


def run_window(
    ctx: TraceContext,
    window: PerceiveWindow,
    perceiver: Perceiver | None = None,
) -> Observation:
    """Run a single window through the perception layer."""
    p = perceiver or make_default_perceiver()
    return p.perceive(ctx, window)


__all__ = ["run_window", "make_default_perceiver"]
