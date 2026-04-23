"""Langfuse wrapper used by every VLM/LLM adapter in Phase 1.

PITFALLS.md §"observability afterthought" — Langfuse must be wired from day 1, every call.
Failures are logged but never raise, so observability outages do not break the pipeline.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache, wraps
from typing import Any, TypeVar

from sva.config import settings

try:
    from langfuse import Langfuse  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - langfuse missing in dev env
    Langfuse = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class TraceContext:
    """Metadata attached to every Langfuse trace emitted by a VLM/LLM call."""
    stage: str           # "perceive" | "interpret"
    model: str           # e.g. "gemini-2.5-flash", "claude-sonnet-4-5"
    video_id: str
    game_id: str
    window_id: str | None = None
    point_id: str | None = None
    point_ordinal: int | None = None
    prompt_version_hash: str | None = None  # OBS-02: short SHA-256 hex of the prompt string (12 chars)
    latency_ms: int | None = None
    retry_count: int | None = None
    terminal_status: str | None = None
    # Compute as: hashlib.sha256(prompt.encode()).hexdigest()[:12]
    # Example: hashlib.sha256("Analyze this frame".encode()).hexdigest()[:12] == "3b5a2c1d4e6f"


@lru_cache(maxsize=1)
def get_langfuse():
    """Return a process-wide Langfuse client, or None if init fails."""
    if Langfuse is None:
        logger.warning("langfuse SDK not installed; traces disabled")
        return None
    try:
        return Langfuse(
            public_key=settings.langfuse_public_key.get_secret_value(),
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            host=settings.langfuse_host,
        )
    except Exception as exc:  # pragma: no cover - network / auth edge
        logger.warning("Langfuse init failed; traces disabled: %s", exc)
        return None


def observe_call(
    stage: str,
    model: str,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that wraps a callable returning a (result, cost_usd, input_tokens, output_tokens, ctx) tuple.

    The wrapped function MUST accept a TraceContext as its first positional argument and return
    a 5-tuple: (result, cost_usd: Decimal, input_tokens: int, output_tokens: int, updated_ctx: TraceContext).
    The decorator records a Langfuse trace and returns just `result`.

    Langfuse failures never propagate.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def _update_trace(trace: Any, cost_usd: Decimal, in_tokens: int, out_tokens: int, updated_ctx: TraceContext) -> None:
            trace.update(
                output={
                    "cost_usd": str(cost_usd),
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                    "latency_ms": updated_ctx.latency_ms,
                    "retry_count": updated_ctx.retry_count,
                    "terminal_status": updated_ctx.terminal_status,
                    "prompt_version_hash": updated_ctx.prompt_version_hash,
                },
            )
            trace.score(name="cost_usd", value=float(cost_usd))
            trace.score(name="input_tokens", value=float(in_tokens))
            trace.score(name="output_tokens", value=float(out_tokens))
            if updated_ctx.latency_ms is not None:
                trace.score(name="latency_ms", value=float(updated_ctx.latency_ms))

        @wraps(fn)
        def wrapper(ctx: TraceContext, *args: Any, **kwargs: Any) -> T:
            lf = get_langfuse()
            trace = None
            if lf is not None:
                try:
                    trace = lf.trace(
                        name=f"{stage}.call",
                        metadata={
                            "stage": stage,
                            "model": model,
                            "video_id": ctx.video_id,
                            "game_id": ctx.game_id,
                            "window_id": ctx.window_id,
                            "point_id": ctx.point_id,
                            "point_ordinal": ctx.point_ordinal,
                            "prompt_version_hash": ctx.prompt_version_hash,
                        },
                        tags=[stage, model, f"video:{ctx.video_id}"],
                    )
                except Exception as exc:  # pragma: no cover
                    logger.warning("Langfuse trace create failed: %s", exc)
                    trace = None

            try:
                result_tuple = fn(ctx, *args, **kwargs)
            except Exception as exc:
                if trace is not None:
                    try:
                        updated_ctx = getattr(exc, "updated_ctx", None) or TraceContext(
                            stage=ctx.stage,
                            model=ctx.model,
                            video_id=ctx.video_id,
                            game_id=ctx.game_id,
                            window_id=ctx.window_id,
                            point_id=ctx.point_id,
                            point_ordinal=ctx.point_ordinal,
                            prompt_version_hash=ctx.prompt_version_hash,
                            terminal_status="error",
                        )
                        _update_trace(trace, Decimal("0"), 0, 0, updated_ctx)
                    except Exception as trace_exc:  # pragma: no cover
                        logger.warning("Langfuse trace update failed: %s", trace_exc)
                raise

            # Contract: (result, cost_usd, input_tokens, output_tokens, updated_ctx)
            result, cost_usd, in_tokens, out_tokens, updated_ctx = result_tuple

            if trace is not None:
                try:
                    _update_trace(trace, cost_usd, in_tokens, out_tokens, updated_ctx)
                except Exception as exc:  # pragma: no cover
                    logger.warning("Langfuse trace update failed: %s", exc)

            # Persist cost to jobs table regardless of Langfuse state.
            try:
                from sva.observability.cost import record_job_cost

                record_job_cost(ctx.game_id, cost_usd)
            except Exception as exc:
                logger.warning("record_job_cost failed: %s", exc)

            return result  # type: ignore[return-value]

        return wrapper

    return decorator


def prompt_version_hash(prompt: str) -> str:
    """Return the canonical 12-char prompt hash used for cache identity."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


__all__ = ["get_langfuse", "observe_call", "prompt_version_hash", "TraceContext"]
