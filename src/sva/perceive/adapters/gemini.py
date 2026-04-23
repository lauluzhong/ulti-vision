"""Gemini 2.5 Flash VLM adapter.

Phase 1 scope: emit a minimal Observation and exercise the Langfuse trace + cost path.
Phase 3 replaces the stubbed body with real `google.genai` File API calls + structured output.
The public contract (Perceiver Protocol) does not change between phases.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sva.models import (
    DiscObservation,
    ModelMetadata,
    Observation,
    PlayerCounts,
    SceneObservation,
)
from sva.observability import TraceContext, observe_call
from sva.observability.cost import estimate_gemini_cost
from sva.perceive.adapters.base import PerceiveWindow

_MODEL_ID = "gemini-2.5-flash"
_VERSION = "phase1-stub-v0"


@observe_call(stage="perceive", model=_MODEL_ID)
def _call_gemini(
    ctx: TraceContext,
    window: PerceiveWindow,
) -> tuple[Observation, Decimal, int, int, TraceContext]:
    """Phase 1 stub: emit a minimal Observation + fake token counts.

    The real Gemini call lands in Phase 3. For Phase 1 we only prove:
        - the Observation conforms to the versioned schema
        - the Langfuse trace + cost path is wired
    """
    input_tokens = 100
    output_tokens = 50
    cost = estimate_gemini_cost(input_tokens, output_tokens, model=_MODEL_ID)

    observation = Observation(
        observation_id=f"obs_{uuid.uuid4().hex[:12]}",
        window_id=window.window_id,
        video_id=window.video_id,
        video_ts_start_ms=window.video_ts_start_ms,
        video_ts_end_ms=window.video_ts_end_ms,
        observation_ts_ms=(window.video_ts_start_ms + window.video_ts_end_ms) // 2,
        scene=SceneObservation(),
        disc=DiscObservation(),
        players=PlayerCounts(),
        actions_detected=[],
        text_observed=[],
        free_form_note="phase1 stubbed observation",
        model=ModelMetadata(provider="gemini", model_id=_MODEL_ID, version=_VERSION),
        confidence_overall=0.0,
    )
    return (observation, cost, input_tokens, output_tokens, ctx)


class GeminiPerceiver:
    """Phase 1 stub; real API calls land in Phase 3. Shape is final."""

    model_id: str = _MODEL_ID
    provider: str = "gemini"

    def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation:
        enriched = TraceContext(
            stage="perceive",
            model=_MODEL_ID,
            video_id=ctx.video_id,
            game_id=ctx.game_id,
            window_id=window.window_id,
            point_id=ctx.point_id,
            point_ordinal=ctx.point_ordinal,
        )
        return _call_gemini(enriched, window)


__all__ = ["GeminiPerceiver"]
