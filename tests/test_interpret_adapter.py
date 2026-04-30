"""Interpret adapter tests for the Gemini Flash seam (v0 default)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from sva.models import (
    DiscObservation,
    MemoryRecord,
    MemorySource,
    ModelMetadata,
    Observation,
    PlayerCounts,
    SceneObservation,
)
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
def test_gemini_interpreter_emits_valid_event_for_smoke_input(monkeypatch):
    """Smoke: a Gemini call returning one valid event lands in the DB with cost recorded.

    Stubs the google.genai client so this test runs without API credentials —
    we're verifying contract conformance, not real model output quality.
    """
    from sva.db import get_engine
    from sva.interpret import GeminiInterpreter

    game_id = "test_interpret_game_1"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text("INSERT INTO jobs (game_id, video_id, status) VALUES (:g, :v, 'streaming')"),
            {"g": game_id, "v": "vid_test"},
        )

    fake_response = SimpleNamespace(
        parsed=[
            {
                "schema_version": "1.0",
                "event_id": "evt_smoke_1",
                "game_id": game_id,
                "point_id": f"{game_id}:pt_001",
                "point_ordinal": 1,
                "video_ts_ms": 1000,
                "in_point_ts_ms": 1000,
                "type": "unknown",
                "team": "unknown",
                "source_observations": ["obs_win_1", "obs_win_2"],
                "rule_refs": [],
                "memory_refs": [],
                "confidence": 0.5,
                "warnings": [],
                "model": {"provider": "gemini", "model_id": "ignored", "version": "ignored"},
            }
        ],
        text="",
        usage_metadata=SimpleNamespace(prompt_token_count=500, candidates_token_count=80),
    )
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: fake_response)
    )
    monkeypatch.setattr("sva.interpret.adapters.gemini._get_client", lambda: fake_client)

    ctx = TraceContext(
        stage="interpret",
        model="gemini-2.5-flash",
        video_id="vid_test",
        game_id=game_id,
        point_id=f"{game_id}:pt_001",
        point_ordinal=1,
    )
    obs_list = [_dummy_obs(window_id="win_1"), _dummy_obs(window_id="win_2")]
    events = GeminiInterpreter().interpret(ctx, obs_list, retrieved=[])
    assert len(events) == 1
    event = events[0]

    assert event.schema_version == "1.0"
    assert event.model.provider == "gemini"
    assert event.model.model_id == "gemini-2.5-flash"
    assert event.point_id == f"{game_id}:pt_001"
    assert event.point_ordinal == 1
    assert event.in_point_ts_ms == 1000

    # OBS-01: cost was recorded (Gemini token rates, but > 0).
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
    ctx = TraceContext(
        stage="interpret",
        model="dummy-llm",
        video_id="v",
        game_id="g",
        point_id="g:pt_001",
        point_ordinal=1,
    )
    events = run_point(ctx, observations=[], interpreter=d)
    assert len(events) == 1
    event = events[0]
    assert event.model.provider == "dummy"
    assert event.point_id == "g:pt_001"
    assert event.type == "unknown"


def test_gemini_interpreter_parses_multiple_events_and_defaults_best_effort_fields(monkeypatch):
    """Verify per-event normalization: completion -> throw_type/pass_direction default
    to 'unknown', turnover -> turnover_subtype defaults to 'unknown', memory_refs
    propagate, prompt_version_hash gets stamped, model.provider becomes 'gemini'.
    """
    from sva.interpret import GeminiInterpreter

    parsed_events = [
        {
            "schema_version": "1.0",
            "event_id": "evt_1",
            "game_id": "game_x",
            "point_id": "game_x:pt_001",
            "point_ordinal": 1,
            "video_ts_ms": 1000,
            "in_point_ts_ms": 1000,
            "type": "completion",
            "team": "dark",
            "source_observations": ["obs_win_1"],
            "rule_refs": ["WFDF-12.1"],
            "memory_refs": [],
            "confidence": 0.8,
            "warnings": [],
            "model": {"provider": "gemini", "model_id": "ignored", "version": "ignored"},
        },
        {
            "schema_version": "1.0",
            "event_id": "evt_2",
            "game_id": "game_x",
            "point_id": "game_x:pt_001",
            "point_ordinal": 1,
            "video_ts_ms": 1500,
            "in_point_ts_ms": 1500,
            "type": "turnover",
            "team": "light",
            "source_observations": ["obs_win_2"],
            "rule_refs": ["WFDF-13.2"],
            "memory_refs": [],
            "confidence": 0.6,
            "warnings": [],
            "model": {"provider": "gemini", "model_id": "ignored", "version": "ignored"},
        },
    ]
    fake_response = SimpleNamespace(
        parsed=parsed_events,
        text="",
        usage_metadata=SimpleNamespace(prompt_token_count=600, candidates_token_count=180),
    )
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: fake_response)
    )
    monkeypatch.setattr("sva.interpret.adapters.gemini._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
    monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)

    ctx = TraceContext(
        stage="interpret",
        model="gemini-2.5-flash",
        video_id="vid_test",
        game_id="game_x",
        point_id="game_x:pt_001",
        point_ordinal=1,
    )
    retrieved = [
        MemoryRecord(
            memory_id="mem_turnover_hint",
            kind="correction",
            tags=["turnover"],
            scope="coach:coach_1",
            source=MemorySource(origin="correction", source_coach_id="coach_1"),
            created_at=datetime.now(timezone.utc),
        )
    ]
    events = GeminiInterpreter().interpret(
        ctx,
        [_dummy_obs(window_id="win_1"), _dummy_obs(window_id="win_2")],
        retrieved=retrieved,
    )

    assert len(events) == 2
    assert events[0].type == "completion"
    assert events[0].throw_type == "unknown"
    assert events[0].pass_direction == "unknown"
    assert events[1].type == "turnover"
    assert events[1].turnover_subtype == "unknown"
    assert events[0].prompt_version_hash is not None
    assert events[0].model.provider == "gemini"
    assert events[0].model.model_id == "gemini-2.5-flash"
    assert events[0].memory_refs == ["mem_turnover_hint"]
    assert events[1].rule_refs == ["WFDF-13.2"]


def test_gemini_interpreter_raises_on_invalid_structured_output(monkeypatch):
    """When Gemini returns a non-list payload, the adapter raises ValueError."""
    from sva.interpret import GeminiInterpreter

    fake_response = SimpleNamespace(
        parsed={"not": "a list of events"},
        text="",
        usage_metadata=SimpleNamespace(prompt_token_count=500, candidates_token_count=50),
    )
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: fake_response)
    )
    monkeypatch.setattr("sva.interpret.adapters.gemini._get_client", lambda: fake_client)
    monkeypatch.setattr("sva.observability.langfuse.get_langfuse", lambda: None)
    monkeypatch.setattr("sva.observability.cost.record_job_cost", lambda game_id, delta_usd: None)

    ctx = TraceContext(
        stage="interpret",
        model="gemini-2.5-flash",
        video_id="vid_test",
        game_id="game_x",
        point_id="game_x:pt_001",
        point_ordinal=1,
    )

    with pytest.raises(ValueError):
        GeminiInterpreter().interpret(ctx, [_dummy_obs(window_id="win_1")], retrieved=[])
