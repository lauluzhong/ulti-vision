"""Tests for Phase 6 polling-first job status API."""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sva.jobs_dao import JobRecord

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

def _job(status: str = "running", stage: str = "perceive") -> JobRecord:
    return JobRecord(
        game_id="game_jobs_001",
        video_id="vid_jobs_001",
        status=status,
        stage=stage,
        progress={"points_total": 10, "points_completed": 3, "windows_total": 20, "windows_completed": 7},
        error_message=None,
        cost_usd=Decimal("0.12"),
        source_path="tests/fixtures/cfr_baseline.mp4",
        source_kind="local_file",
        source_url=None,
        duration_s=10.0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def test_jobs_api_returns_persisted_status(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda job_id: _job())

    client = TestClient(create_app())
    response = client.get("/jobs/game_jobs_001")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "game_jobs_001",
        "game_id": "game_jobs_001",
        "status": "running",
        "stage": "perceive",
        "progress": {
            "points_total": 10,
            "points_completed": 3,
            "windows_total": 20,
            "windows_completed": 7,
        },
        "error_message": None,
    }

def test_jobs_api_returns_404_for_unknown_job(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda job_id: None)

    client = TestClient(create_app())
    response = client.get("/jobs/unknown")

    assert response.status_code == 404
    assert "unknown job" in response.json()["detail"].lower()
