"""Tests for the async Phase 6 ingest submission API surface."""

from __future__ import annotations

import importlib

import pytest

from sva.jobs_dao import JobRecord

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _fake_job(source_kind: str, source_url: str | None = None) -> JobRecord:
    from datetime import datetime, timezone
    from decimal import Decimal

    return JobRecord(
        game_id="game_test",
        video_id=None,
        status="queued",
        stage="queued",
        progress={"target_fps": 1},
        error_message=None,
        cost_usd=Decimal("0"),
        source_path="tests/fixtures/cfr_baseline.mp4",
        source_kind=source_kind,
        source_url=source_url,
        duration_s=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_ingest_api_accepts_file_upload(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    enqueued: list[str] = []

    def _fake_submit(path, game_id=None, target_fps=1):
        assert target_fps == 1
        return _fake_job("local_file")

    monkeypatch.setattr(api_module, "submit_local_job", _fake_submit)
    monkeypatch.setattr(api_module, "enqueue_job", lambda job_id: enqueued.append(job_id))

    client = TestClient(create_app())
    response = client.post(
        "/ingest",
        files={"upload": ("clip.mp4", b"video", "video/mp4")},
        data={"fps": "1"},
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == "game_test"
    assert response.json()["source_kind"] == "local_file"
    assert enqueued == ["game_test"]


def test_ingest_api_accepts_approved_url(monkeypatch):
    from sva.api.app import create_app

    api_module = importlib.import_module("sva.api.app")
    enqueued: list[str] = []

    def _fake_submit(url, caller_id, ack_rights, game_id=None, target_fps=1):
        assert ack_rights is True
        assert caller_id == "api-test"
        return _fake_job("public_url", source_url=url)

    monkeypatch.setattr(api_module, "submit_remote_job", _fake_submit)
    monkeypatch.setattr(api_module, "enqueue_job", lambda job_id: enqueued.append(job_id))

    client = TestClient(create_app())
    response = client.post(
        "/ingest",
        data={
            "url": "https://www.youtube.com/watch?v=abc123",
            "ack_rights": "true",
            "caller_id": "api-test",
        },
    )

    assert response.status_code == 202
    assert response.json()["source_kind"] == "public_url"
    assert response.json()["job_id"] == "game_test"
    assert enqueued == ["game_test"]


def test_ingest_api_rejects_url_without_rights_ack():
    from sva.api.app import create_app

    client = TestClient(create_app())
    response = client.post(
        "/ingest",
        data={"url": "https://www.youtube.com/watch?v=abc123"},
    )

    assert response.status_code == 400
    assert "rights" in response.json()["detail"].lower()
