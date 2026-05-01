"""Tests for Phase 7 point-boundary API routes."""

from __future__ import annotations

import importlib

import pytest

from sva.jobs_dao import JobRecord
from sva.points.types import BoundarySignal, PointRecord

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

def _job() -> JobRecord:
    from datetime import datetime, timezone
    from decimal import Decimal

    return JobRecord(
        game_id="game_points_001",
        video_id="vid_points_001",
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

def _point(point_id: str, ordinal: int, start_ms: int, end_ms: int) -> PointRecord:
    return PointRecord(
        point_id=point_id,
        game_id="game_points_001",
        point_ordinal=ordinal,
        start_video_ts_ms=start_ms,
        end_video_ts_ms=end_ms,
        confidence=0.95,
        boundary_evidence=[
            BoundarySignal(source="manual", video_ts_ms=start_ms, confidence=1.0),
        ],
    )

def test_points_api_lists_current_boundaries(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(
        api_module,
        "list_points",
        lambda game_id: [
            _point("game_points_001:pt_001", 1, 0, 10000),
            _point("game_points_001:pt_002", 2, 10001, 22000),
        ],
    )

    client = TestClient(create_app())
    response = client.get("/games/game_points_001/points")

    assert response.status_code == 200
    assert response.json() == {
        "game_id": "game_points_001",
        "points": [
            {
                "point_id": "game_points_001:pt_001",
                "point_ordinal": 1,
                "start_video_ts_ms": 0,
                "end_video_ts_ms": 10000,
                "confidence": 0.95,
                "boundary_evidence": [
                    {
                        "source": "manual",
                        "video_ts_ms": 0,
                        "confidence": 1.0,
                        "details": {},
                    }
                ],
            },
            {
                "point_id": "game_points_001:pt_002",
                "point_ordinal": 2,
                "start_video_ts_ms": 10001,
                "end_video_ts_ms": 22000,
                "confidence": 0.95,
                "boundary_evidence": [
                    {
                        "source": "manual",
                        "video_ts_ms": 10001,
                        "confidence": 1.0,
                        "details": {},
                    }
                ],
            },
        ],
    }

def test_points_api_updates_boundaries_and_reports_rebucket_counts(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    service_module = importlib.import_module("sva.points.service")
    captured: dict[str, object] = {}

    def _fake_replace(game_id, patches):
        captured["game_id"] = game_id
        captured["patches"] = patches
        return service_module.PointBoundaryUpdateResult(
            game_id=game_id,
            points=[
                _point("game_points_001:pt_001", 1, 0, 12000),
                _point("game_points_001:pt_002", 2, 12001, 24000),
            ],
            events_rebucketed=2,
            observations_rebucketed=1,
        )

    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(api_module, "replace_point_boundaries", _fake_replace)

    client = TestClient(create_app())
    response = client.put(
        "/games/game_points_001/points",
        json={
            "points": [
                {"start_video_ts_ms": 0, "end_video_ts_ms": 12000},
                {"start_video_ts_ms": 12001, "end_video_ts_ms": 24000},
            ]
        },
    )

    assert response.status_code == 200
    assert captured["game_id"] == "game_points_001"
    patches = captured["patches"]
    assert len(patches) == 2
    assert getattr(patches[0], "start_video_ts_ms") == 0
    assert getattr(patches[1], "end_video_ts_ms") == 24000
    assert response.json()["events_rebucketed"] == 2
    assert response.json()["observations_rebucketed"] == 1

def test_points_api_maps_boundary_validation_errors_to_400(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(
        api_module,
        "replace_point_boundaries",
        lambda game_id, patches: (_ for _ in ()).throw(
            ValueError("point boundaries cannot be edited after corrections exist for this game")
        ),
    )

    client = TestClient(create_app())
    response = client.put(
        "/games/game_points_001/points",
        json={"points": [{"start_video_ts_ms": 0, "end_video_ts_ms": 10000}]},
    )

    assert response.status_code == 400
    assert "cannot be edited after corrections exist" in response.json()["detail"]
