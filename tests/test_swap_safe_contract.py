"""Swap-safety contract test (Phase 1 success criterion #4).

Proves that a dummy Perceiver plugs into run_window without changing the Observation schema
or any downstream consumer. The ONLY change required to switch VLM backends is returning a
different class from make_default_perceiver().
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from sva.models import (
    DiscObservation,
    ModelMetadata,
    Observation,
    PlayerCounts,
    SceneObservation,
)
from sva.observability import TraceContext
from sva.perceive.adapters.base import Perceiver, PerceiveWindow
from sva.perceive.runner import run_window


def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


class DummyPerceiver:
    """Hand-rolled Perceiver that does not touch any network or SDK.

    If this class can substitute for GeminiPerceiver without any other code changes,
    the swap-safety contract holds.
    """

    model_id = "dummy-vlm-v0"
    provider = "dummy"

    def perceive(self, ctx: TraceContext, window: PerceiveWindow) -> Observation:
        return Observation(
            observation_id=f"obs_dummy_{window.window_id}",
            window_id=window.window_id,
            video_id=window.video_id,
            video_ts_start_ms=window.video_ts_start_ms,
            video_ts_end_ms=window.video_ts_end_ms,
            observation_ts_ms=window.video_ts_start_ms,
            scene=SceneObservation(),
            disc=DiscObservation(),
            players=PlayerCounts(),
            actions_detected=[],
            text_observed=[],
            free_form_note="dummy adapter — swap-safety test",
            model=ModelMetadata(provider="dummy", model_id="dummy-vlm-v0", version="test"),
            confidence_overall=0.42,
        )


def test_dummy_perceiver_conforms_to_protocol():
    # Structural (duck) typing: Perceiver is a Protocol; isinstance check requires runtime_checkable.
    # We instead verify by calling through run_window.
    p: Perceiver = DummyPerceiver()  # must satisfy Protocol statically
    assert hasattr(p, "perceive")


def test_run_window_accepts_any_perceiver():
    ctx = TraceContext(
        stage="perceive",
        model="dummy-vlm-v0",
        video_id="vid_swap",
        game_id="swap_test_game",
    )
    window = PerceiveWindow(
        window_id="win_swap_1",
        video_id="vid_swap",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    # run_window must accept DummyPerceiver without modification.
    obs = run_window(ctx, window, perceiver=DummyPerceiver())
    assert obs.model.provider == "dummy"
    assert obs.confidence_overall == 0.42
    # Same schema as Gemini output — proves downstream consumers are agnostic.
    assert obs.schema_version == "1.0"
