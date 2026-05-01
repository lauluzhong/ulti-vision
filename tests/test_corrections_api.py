"""Tests for Phase 6 corrections submission API."""

from __future__ import annotations

import importlib

import pytest

from sva.jobs_dao import JobRecord

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

def _job() -> JobRecord:
    from datetime import datetime, timezone
    from decimal import Decimal

    return JobRecord(
        game_id="game_corr_001",
        video_id="vid_corr_001",
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

def test_corrections_api_persists_immutable_correction_and_memory(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    service_module = importlib.import_module("sva.memory.service")
    captured: dict[str, object] = {}

    def _fake_submit(game_id, payload):
        captured["game_id"] = game_id
        captured["payload"] = payload
        return service_module.CorrectionSubmissionResult(
            correction_id="corr_http_001",
            game_id=game_id,
            point_id=payload.point_id,
            point_ordinal=payload.point_ordinal,
            coach_id=payload.coach_id,
            correction_type=payload.correction_type,
            created_memory_ids=["mem_http_001"],
        )

    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(api_module, "submit_correction", _fake_submit)

    client = TestClient(create_app())
    response = client.post(
        "/games/game_corr_001/corrections",
        json={
            "point_id": "game_corr_001:pt_001",
            "point_ordinal": 1,
            "source_event_id": "evt_001",
            "coach_id": "coach_123",
            "correction_type": "reclassify",
            "original_event": {"type": "turnover", "team": "light"},
            "proposed_event": {"type": "completion", "team": "dark"},
            "source_memory_refs": ["mem_seed_001"],
            "note": "disc never hit ground",
        },
    )

    assert response.status_code == 201
    assert captured["game_id"] == "game_corr_001"
    payload = captured["payload"]
    assert getattr(payload, "coach_id") == "coach_123"
    assert response.json() == {
        "correction_id": "corr_http_001",
        "game_id": "game_corr_001",
        "point_id": "game_corr_001:pt_001",
        "point_ordinal": 1,
        "coach_id": "coach_123",
        "correction_type": "reclassify",
        "created_memory_ids": ["mem_http_001"],
    }

def test_corrections_api_records_coach_provenance(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    service_module = importlib.import_module("sva.memory.service")
    seen: list[str] = []

    def _fake_submit(game_id, payload):
        seen.append(payload.coach_id)
        return service_module.CorrectionSubmissionResult(
            correction_id="corr_http_002",
            game_id=game_id,
            point_id=payload.point_id,
            point_ordinal=payload.point_ordinal,
            coach_id=payload.coach_id,
            correction_type=payload.correction_type,
            created_memory_ids=["mem_http_002"],
        )

    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(api_module, "submit_correction", _fake_submit)

    client = TestClient(create_app())
    response = client.post(
        "/games/game_corr_001/corrections",
        json={
            "point_id": "game_corr_001:pt_002",
            "point_ordinal": 2,
            "coach_id": "coach_provenance",
            "correction_type": "mark_missed",
            "proposed_event": {"type": "goal", "team": "dark"},
        },
    )

    assert response.status_code == 201
    assert seen == ["coach_provenance"]

def test_corrections_api_rejects_invalid_payload_before_service_call(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(
        api_module,
        "submit_correction",
        lambda game_id, payload: (_ for _ in ()).throw(AssertionError("service should not run")),
    )

    client = TestClient(create_app())
    response = client.post(
        "/games/game_corr_001/corrections",
        json={
            "point_id": "game_corr_001:pt_001",
            "point_ordinal": 1,
            "coach_id": "coach_123",
            "correction_type": "reclassify",
            "original_event": {"type": "turnover"},
        },
    )

    assert response.status_code == 422
