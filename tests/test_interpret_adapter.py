"""Phase 1 tests: ClaudeInterpreter stub emits a valid Event + exercises observability."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from sva.models import DiscObservation, ModelMetadata, Observation, PlayerCounts, SceneObservation
from sva.observability import TraceContext


def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _dummy_obs(window_id="win_1", video_id="vid_test") -> Observation:
    return Observation(
        observation_id=f"obs_{window_id}",
        window_id=window_id,
        video_id=video_id,
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        observation_ts_ms=1000,
        scene=SceneObservation(),
        disc=DiscObservation(),
        players=PlayerCounts(),
        actions_detected=[],
        text_observed=[],
        model=ModelMetadata(provider="dummy", model_id="dummy", version="v0"),
        confidence_overall=0.5,
    )


@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
def test_claude_interpreter_emits_valid_event():
    from sva.db import get_engine
    from sva.interpret import ClaudeInterpreter

    game_id = "test_interpret_game_1"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text("INSERT INTO jobs (game_id, video_id, status) VALUES (:g, :v, 'streaming')"),
            {"g": game_id, "v": "vid_test"},
        )

    ctx = TraceContext(
        stage="interpret",
        model="claude-sonnet-4-5",
        video_id="vid_test",
        game_id=game_id,
        point_id=f"{game_id}:pt_001",
        point_ordinal=1,
    )
    obs_list = [_dummy_obs(window_id="win_1"), _dummy_obs(window_id="win_2")]
    event = ClaudeInterpreter().interpret(ctx, obs_list, retrieved=[])

    assert event.schema_version == "1.0"
    assert event.model.provider == "anthropic"
    assert event.model.model_id == "claude-sonnet-4-5"
    assert event.point_id == f"{game_id}:pt_001"
    assert event.point_ordinal == 1
    assert event.in_point_ts_ms == 1000
    assert event.type == "unknown"
    assert len(event.source_observations) == 2

    # OBS-01: cost was recorded
    with get_engine().connect() as conn:
        cost = conn.execute(
            text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()
    assert float(cost) > 0

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})


def test_run_point_accepts_custom_interpreter():
    """Swap-safe: a dummy Interpreter substitutes without code changes."""
    from sva.interpret.adapters.base import Interpreter
    from sva.interpret.runner import run_point
    from sva.models import Event

    class DummyInterpreter:
        def interpret(self, ctx, observations, retrieved):
            return Event(
                event_id="evt_dummy",
                game_id=ctx.game_id,
                point_id=ctx.point_id or f"{ctx.game_id}:pt_001",
                point_ordinal=ctx.point_ordinal or 1,
                video_ts_ms=0,
                in_point_ts_ms=0,
                type="unknown",
                team="unknown",
                model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
            )

    d: Interpreter = DummyInterpreter()
    ctx = TraceContext(stage="interpret", model="dummy-llm", video_id="v", game_id="g", point_id="g:pt_001", point_ordinal=1)
    event = run_point(ctx, observations=[], interpreter=d)
    assert event.model.provider == "dummy"
    assert event.point_id == "g:pt_001"
    assert event.type == "unknown"
