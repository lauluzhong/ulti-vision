"""Interpret adapter tests for the current Claude seam."""

from __future__ import annotations

from types import SimpleNamespace

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
    events = ClaudeInterpreter().interpret(ctx, obs_list, retrieved=[])
    assert len(events) == 1
    event = events[0]

    assert event.schema_version == "1.0"
    assert event.model.provider == "anthropic"
    assert event.model.model_id == "claude-sonnet-4-5"
    assert event.point_id == f"{game_id}:pt_001"
    assert event.point_ordinal == 1
    assert event.in_point_ts_ms == 1000
    assert event.type == "unknown"
    assert len(event.source_observations) == 2
    assert event.prompt_version_hash is None

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
            return [
                Event(
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
            ]

    d: Interpreter = DummyInterpreter()
    ctx = TraceContext(stage="interpret", model="dummy-llm", video_id="v", game_id="g", point_id="g:pt_001", point_ordinal=1)
    events = run_point(ctx, observations=[], interpreter=d)
    assert len(events) == 1
    event = events[0]
    assert event.model.provider == "dummy"
    assert event.point_id == "g:pt_001"
    assert event.type == "unknown"


def test_claude_interpreter_parses_multiple_events_and_defaults_best_effort_fields(monkeypatch):
    from anthropic.types import TextBlock, Usage
    from sva.interpret import ClaudeInterpreter

    fake_message = SimpleNamespace(
        content=[
            TextBlock(
                type="text",
                text=(
                    '[{"event_id":"evt_1","game_id":"game_x","point_id":"game_x:pt_001","point_ordinal":1,'
                    '"video_ts_ms":1000,"in_point_ts_ms":1000,"type":"completion","team":"dark",'
                    '"source_observations":["obs_win_1"],"rule_refs":["USAU-3"],"memory_refs":[],'
                    '"confidence":0.8,"warnings":[],"model":{"provider":"anthropic","model_id":"ignored","version":"ignored"}},'
                    '{"event_id":"evt_2","game_id":"game_x","point_id":"game_x:pt_001","point_ordinal":1,'
                    '"video_ts_ms":1500,"in_point_ts_ms":1500,"type":"turnover","team":"light",'
                    '"source_observations":["obs_win_2"],"rule_refs":["USAU-13"],"memory_refs":[],'
                    '"confidence":0.6,"warnings":[],"model":{"provider":"anthropic","model_id":"ignored","version":"ignored"}}]'
                ),
            )
        ],
        usage=Usage(input_tokens=600, output_tokens=180),
    )
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: fake_message))
    monkeypatch.setattr("sva.interpret.adapters.claude._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
    monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)

    ctx = TraceContext(
        stage="interpret",
        model="claude-sonnet-4-5",
        video_id="vid_test",
        game_id="game_x",
        point_id="game_x:pt_001",
        point_ordinal=1,
    )
    events = ClaudeInterpreter().interpret(ctx, [_dummy_obs(window_id="win_1"), _dummy_obs(window_id="win_2")], retrieved=[])

    assert len(events) == 2
    assert events[0].type == "completion"
    assert events[0].throw_type == "unknown"
    assert events[0].pass_direction == "unknown"
    assert events[1].type == "turnover"
    assert events[1].turnover_subtype == "unknown"
    assert events[0].prompt_version_hash is not None
    assert events[0].model.model_id == "claude-sonnet-4-5"
    assert events[1].rule_refs == ["USAU-13"]


def test_claude_interpreter_raises_on_invalid_structured_output(monkeypatch):
    from anthropic.types import TextBlock, Usage
    from sva.interpret import ClaudeInterpreter

    fake_message = SimpleNamespace(
        content=[TextBlock(type="text", text='{"not":"a list of events"}')],
        usage=Usage(input_tokens=500, output_tokens=50),
    )
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: fake_message))
    monkeypatch.setattr("sva.interpret.adapters.claude._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
    monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)

    ctx = TraceContext(
        stage="interpret",
        model="claude-sonnet-4-5",
        video_id="vid_test",
        game_id="game_x",
        point_id="game_x:pt_001",
        point_ordinal=1,
    )

    with pytest.raises(ValueError):
        ClaudeInterpreter().interpret(ctx, [_dummy_obs(window_id="win_1")], retrieved=[])
