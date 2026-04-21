"""Claude Sonnet 4.5 LLM adapter.

Phase 1 scope: emit a minimal Event with type='unknown' and exercise the Langfuse trace path.
Phase 4 replaces the body with real anthropic SDK calls + rules composition + structured output.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sva.models import Event, MemoryRecord, ModelMetadata, Observation
from sva.observability import TraceContext, observe_call
from sva.observability.cost import estimate_claude_cost

_MODEL_ID = "claude-sonnet-4-5"
_VERSION = "phase1-stub-v0"


@observe_call(stage="interpret", model=_MODEL_ID)
def _call_claude(
    ctx: TraceContext,
    observations: list[Observation],
    retrieved: list[MemoryRecord],
) -> tuple[Event, Decimal, int, int, TraceContext]:
    """Phase 1 stub: minimal Event emission, observability path exercised."""
    input_tokens = 500 + 100 * len(observations) + 80 * len(retrieved)
    output_tokens = 100
    cost = estimate_claude_cost(input_tokens, output_tokens, model=_MODEL_ID)

    event = Event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        game_id=ctx.game_id,
        point_id=ctx.point_id,
        video_ts_ms=observations[0].observation_ts_ms if observations else 0,
        type="unknown",
        team="unknown",
        details={"stub": True, "observations_in": len(observations), "memory_in": len(retrieved)},
        source_observations=[o.observation_id for o in observations],
        memory_refs=[m.memory_id for m in retrieved],
        rule_refs=[],
        confidence=0.0,
        warnings=["phase1 stub — real interpretation lands in Phase 4"],
        model=ModelMetadata(provider="anthropic", model_id=_MODEL_ID, version=_VERSION),
    )
    return (event, cost, input_tokens, output_tokens, ctx)


class ClaudeInterpreter:
    """Phase 1 stub; real API calls land in Phase 4. Contract shape is final."""

    model_id: str = _MODEL_ID
    provider: str = "anthropic"

    def interpret(
        self,
        ctx: TraceContext,
        observations: list[Observation],
        retrieved: list[MemoryRecord],
    ) -> Event:
        enriched = TraceContext(
            stage="interpret",
            model=_MODEL_ID,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=ctx.window_id,
            point_id=ctx.point_id,
        )
        return _call_claude(enriched, observations, retrieved)


__all__ = ["ClaudeInterpreter"]
