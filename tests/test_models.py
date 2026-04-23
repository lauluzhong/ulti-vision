"""Swap-safety contract tests for sva.models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sva.models import (
    SCHEMA_VERSION,
    Event,
    MemoryRecord,
    ModelMetadata,
    Observation,
)


def test_schema_version_is_1_0():
    assert SCHEMA_VERSION == "1.0"


def test_observation_round_trips_json():
    obs = Observation(
        observation_id="obs_01",
        window_id="win_01",
        video_id="vid_01",
        video_ts_start_ms=0,
        video_ts_end_ms=1000,
        observation_ts_ms=500,
        model=ModelMetadata(provider="gemini", model_id="gemini-2.5-flash", version="v1"),
        confidence_overall=0.5,
    )
    payload = obs.model_dump_json()
    rehydrated = Observation.model_validate_json(payload)
    assert rehydrated == obs
    assert rehydrated.schema_version == "1.0"


def test_event_enum_is_closed():
    # Invalid type must raise.
    with pytest.raises(ValidationError):
        Event(
            event_id="e1",
            game_id="g1",
            point_id="g1:pt_001",
            point_ordinal=1,
            video_ts_ms=0,
            in_point_ts_ms=0,
            type="not_a_real_event",  # type: ignore[arg-type]
            model=ModelMetadata(provider="anthropic", model_id="claude-sonnet-4-5", version="v1"),
        )


def test_event_player_id_is_always_none():
    e = Event(
        event_id="e1",
        game_id="g1",
        point_id="g1:pt_001",
        point_ordinal=1,
        video_ts_ms=0,
        in_point_ts_ms=0,
        type="completion",
        model=ModelMetadata(provider="anthropic", model_id="claude-sonnet-4-5", version="v1"),
    )
    assert e.player_id is None
    # Setting player_id to a non-None value should fail (v1 contract).
    with pytest.raises(ValidationError):
        Event(
            event_id="e2",
            game_id="g1",
            point_id="g1:pt_001",
            point_ordinal=1,
            video_ts_ms=0,
            in_point_ts_ms=0,
            type="completion",
            player_id="p_42",  # type: ignore[arg-type]
            model=ModelMetadata(provider="anthropic", model_id="claude-sonnet-4-5", version="v1"),
        )


def test_memory_record_defaults_are_safe():
    mr = MemoryRecord(
        memory_id="mem_01",
        kind="rule",
        created_at=datetime.now(timezone.utc),
    )
    assert mr.scope == "global"
    assert mr.confidence == 0.0
    assert mr.corroborations == 0


def test_no_vendor_field_leakage():
    # The contract is: no field name contains a provider string.
    forbidden = {"gemini", "anthropic", "claude", "gpt", "openai"}
    for cls in (Observation, Event, MemoryRecord):
        for name in cls.model_fields:
            lowered = name.lower()
            for f in forbidden:
                assert f not in lowered, f"{cls.__name__}.{name} leaks vendor name '{f}'"
