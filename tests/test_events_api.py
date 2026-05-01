"""Tests for Phase 6 canonical events API."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from sva.jobs_dao import JobRecord

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

def _job() -> JobRecord:
    from datetime import datetime, timezone
    from decimal import Decimal

    return JobRecord(
        game_id="game_events_001",
        video_id="vid_events_001",
        status="complete",
        stage="complete",
        progress={"points_total": 2, "points_completed": 2},
        error_message=None,
        cost_usd=Decimal("0.22"),
        source_path="tests/fixtures/cfr_baseline.mp4",
        source_kind="local_file",
        source_url=None,
        duration_s=90.0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def _event(
    event_id: str,
    *,
    point_id: str = "game_events_001:pt_001",
    point_ordinal: int = 1,
    video_ts_ms: int = 1000,
    in_point_ts_ms: int = 1000,
    event_type: str = "completion",
    team: str = "dark",
) -> SimpleNamespace:
    return SimpleNamespace(
        event_id=event_id,
        game_id="game_events_001",
        point_id=point_id,
        point_ordinal=point_ordinal,
        video_ts_ms=video_ts_ms,
        in_point_ts_ms=in_point_ts_ms,
        type=event_type,
        team=team,
        turnover_subtype=None,
        throw_type=None,
        pass_direction=None,
        details={"source": "canonical"},
        schema_version="1.0",
        rule_refs=["WFDF-1"],
        memory_refs=["mem_001"],
        confidence=0.91,
        warnings=[],
    )

def test_events_api_returns_canonical_rows_in_stored_order(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(
        api_module,
        "list_event_rows",
        lambda game_id, point_id=None, event_type=None, team=None: [
            _event("evt_001", video_ts_ms=1000),
            _event("evt_002", video_ts_ms=2500, event_type="goal"),
        ],
    )

    client = TestClient(create_app())
    response = client.get("/games/game_events_001/events")

    assert response.status_code == 200
    assert response.json() == {
        "game_id": "game_events_001",
        "events": [
            {
                "event_id": "evt_001",
                "game_id": "game_events_001",
                "point_id": "game_events_001:pt_001",
                "point_ordinal": 1,
                "video_ts_ms": 1000,
                "in_point_ts_ms": 1000,
                "type": "completion",
                "team": "dark",
                "turnover_subtype": None,
                "throw_type": None,
                "pass_direction": None,
                "details": {"source": "canonical"},
                "schema_version": "1.0",
                "rule_refs": ["WFDF-1"],
                "memory_refs": ["mem_001"],
                "confidence": 0.91,
                "warnings": [],
            },
            {
                "event_id": "evt_002",
                "game_id": "game_events_001",
                "point_id": "game_events_001:pt_001",
                "point_ordinal": 1,
                "video_ts_ms": 2500,
                "in_point_ts_ms": 1000,
                "type": "goal",
                "team": "dark",
                "turnover_subtype": None,
                "throw_type": None,
                "pass_direction": None,
                "details": {"source": "canonical"},
                "schema_version": "1.0",
                "rule_refs": ["WFDF-1"],
                "memory_refs": ["mem_001"],
                "confidence": 0.91,
                "warnings": [],
            },
        ],
    }

def test_events_api_passes_filters_to_canonical_dao(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    seen: dict[str, str | None] = {}

    def _fake_list(game_id, point_id=None, event_type=None, team=None):
        seen.update(
            {
                "game_id": game_id,
                "point_id": point_id,
                "event_type": event_type,
                "team": team,
            }
        )
        return [_event("evt_filtered", point_id=point_id or "game_events_001:pt_002", event_type=event_type or "turnover", team=team or "light")]

    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(api_module, "list_event_rows", _fake_list)

    client = TestClient(create_app())
    response = client.get(
        "/games/game_events_001/events",
        params={"point_id": "game_events_001:pt_002", "event_type": "turnover", "team": "light"},
    )

    assert response.status_code == 200
    assert seen == {
        "game_id": "game_events_001",
        "point_id": "game_events_001:pt_002",
        "event_type": "turnover",
        "team": "light",
    }
    assert response.json()["events"][0]["event_id"] == "evt_filtered"

def test_events_api_returns_404_for_unknown_game(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: None)

    client = TestClient(create_app())
    response = client.get("/games/missing/events")

    assert response.status_code == 404
    assert "unknown game" in response.json()["detail"].lower()
