"""Tests for the thin synchronous Phase 2 ingest API surface."""

from __future__ import annotations

import pytest

from sva.ingest.ingest import IngestResult
from sva.ingest.probe import VideoMetadata

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def _fake_result(source_kind: str, source_url: str | None = None) -> IngestResult:
    meta = VideoMetadata(
        path="tests/fixtures/cfr_baseline.mp4",
        duration_s=10.0,
        codec="h264",
        fps_reported=1.0,
        fps_average=1.0,
        container="mp4",
        width=320,
        height=240,
        is_variable_fps=False,
    )
    return IngestResult(
        video_id="vid_test",
        game_id="game_test",
        source_path="tests/fixtures/cfr_baseline.mp4",
        transcoded_path="data/transcoded/vid_test.mp4",
        duration_s=10.0,
        status="ingested",
        windows=[(0, 1000)],
        source_metadata=meta,
        transcoded_metadata=meta,
        source_kind=source_kind,
        source_url=source_url,
    )


def test_ingest_api_accepts_file_upload(monkeypatch):
    from sva.api.app import create_app

    def _fake_ingest(source, game_id=None, target_fps=1):
        assert source.__class__.__name__ == "LocalFileSource"
        return _fake_result("local_file")

    monkeypatch.setattr("sva.api.app.ingest_source", _fake_ingest)

    client = TestClient(create_app())
    response = client.post(
        "/ingest",
        files={"upload": ("clip.mp4", b"video", "video/mp4")},
        data={"fps": "1"},
    )

    assert response.status_code == 200
    assert response.json()["source_kind"] == "local_file"


def test_ingest_api_accepts_approved_url(monkeypatch):
    from sva.api.app import create_app

    def _fake_ingest(source, game_id=None, target_fps=1):
        assert source.__class__.__name__ == "RemoteUrlSource"
        assert source.ack_rights is True
        return _fake_result("public_url", source_url=source.url)

    monkeypatch.setattr("sva.api.app.ingest_source", _fake_ingest)

    client = TestClient(create_app())
    response = client.post(
        "/ingest",
        data={
            "url": "https://www.youtube.com/watch?v=abc123",
            "ack_rights": "true",
            "caller_id": "api-test",
        },
    )

    assert response.status_code == 200
    assert response.json()["source_kind"] == "public_url"
    assert response.json()["source_url"] == "https://www.youtube.com/watch?v=abc123"


def test_ingest_api_rejects_url_without_rights_ack():
    from sva.api.app import create_app

    client = TestClient(create_app())
    response = client.post(
        "/ingest",
        data={"url": "https://www.youtube.com/watch?v=abc123"},
    )

    assert response.status_code == 400
    assert "rights" in response.json()["detail"].lower()
