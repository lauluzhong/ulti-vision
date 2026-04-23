"""Perceive runner — cache-first window execution for any Perceiver."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from sva.models import Observation
from sva.observability import TraceContext, get_langfuse
from sva.observations_dao import list_cached_observations
from sva.perceive.adapters.base import Perceiver, PerceiveWindow
from sva.perceive.adapters.gemini import GeminiPerceiver

logger = logging.getLogger(__name__)
CacheMissHandler = Callable[[Observation, str], None]


def make_default_perceiver() -> Perceiver:
    """Single import-swap point for switching the default VLM backend (D-03).

    Changing the VLM backend ONLY requires editing this function's return statement.
    """
    return GeminiPerceiver()


def _prompt_hash_for_window(perceiver: Perceiver, window: PerceiveWindow) -> str | None:
    prompt_hash_for = getattr(perceiver, "prompt_hash_for", None)
    if callable(prompt_hash_for):
        return prompt_hash_for(window)
    return None


def _emit_cache_hit_trace(ctx: TraceContext) -> None:
    lf = get_langfuse()
    if lf is None:
        return
    try:
        trace = lf.trace(
            name=f"{ctx.stage}.cache_hit",
            metadata={
                "stage": ctx.stage,
                "model": ctx.model,
                "video_id": ctx.video_id,
                "game_id": ctx.game_id,
                "window_id": ctx.window_id,
                "point_id": ctx.point_id,
                "point_ordinal": ctx.point_ordinal,
                "prompt_version_hash": ctx.prompt_version_hash,
            },
            tags=[ctx.stage, ctx.model, f"video:{ctx.video_id}", "cache-hit"],
        )
        trace.update(
            output={
                "cache_hit": True,
                "cost_usd": "0",
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 0,
                "retry_count": 0,
                "terminal_status": "cache_hit",
                "prompt_version_hash": ctx.prompt_version_hash,
            }
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Langfuse cache-hit trace failed: %s", exc)


def run_window(
    ctx: TraceContext,
    window: PerceiveWindow,
    perceiver: Perceiver | None = None,
    on_cache_miss: CacheMissHandler | None = None,
) -> Observation:
    """Run a single window through the perception layer."""
    p = perceiver or make_default_perceiver()
    prompt_hash = _prompt_hash_for_window(p, window)
    effective_ctx = ctx
    if prompt_hash is not None:
        effective_ctx = replace(ctx, prompt_version_hash=prompt_hash)
        cached = list_cached_observations(
            video_id=window.video_id,
            window_id=window.window_id,
            prompt_version_hash=prompt_hash,
        )
        if cached:
            _emit_cache_hit_trace(effective_ctx)
            return cached[0]

    observation = p.perceive(effective_ctx, window)
    if prompt_hash is not None and on_cache_miss is not None:
        on_cache_miss(observation, prompt_hash)
    return observation


__all__ = ["run_window", "make_default_perceiver"]
