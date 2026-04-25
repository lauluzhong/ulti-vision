"""Tests for the Phase 7 playable video route."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from sva.jobs_dao import JobRecord

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _job() -> JobRecord:
    from datetime import datetime, timezone
    from decimal import Decimal

    return JobRecord(
        game_id="game_video_001",
        video_id="vid_video_001",
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


def test_video_api_serves_playable_file(monkeypatch, tmp_path):
    from sva.api.app import create_app

    video_path = tmp_path / "game_video.mp4"
    video_path.write_bytes(b"fake mp4 bytes")

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: _job())
    monkeypatch.setattr(api_module, "_video_path_for_job", lambda job: Path(video_path))

    client = TestClient(create_app())
    response = client.get("/games/game_video_001/video")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.content == b"fake mp4 bytes"


def test_video_api_returns_404_for_unknown_game(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    monkeypatch.setattr(api_module, "get_job", lambda game_id: None)

    client = TestClient(create_app())
    response = client.get("/games/missing/video")

    assert response.status_code == 404
    assert "unknown game" in response.json()["detail"].lower()
