"""Tests for the Phase 2 shared source-intake policy layer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sva.ingest.sources import (
    LocalFileSource,
    PublicUrlAuthenticationRequiredError,
    RemoteUrlSource,
    RightsAckRequiredError,
    UnsupportedSourceError,
    validate_local_source,
    validate_remote_source,
)
from sva.ingest.url_download import DOWNLOAD_DIR, download_public_video


def test_validate_remote_source_accepts_youtube_and_ufa():
    assert validate_remote_source(
        RemoteUrlSource(
            url="https://www.youtube.com/watch?v=abc123",
            ack_rights=True,
            caller_id="builder",
        )
    ).url == "https://www.youtube.com/watch?v=abc123"
    assert validate_remote_source(
        RemoteUrlSource(
            url="https://watchufa.com/video/demo",
            ack_rights=True,
            caller_id="builder",
        )
    ).url == "https://watchufa.com/video/demo"


def test_validate_remote_source_rejects_missing_rights_ack():
    with pytest.raises(RightsAckRequiredError):
        validate_remote_source(
            RemoteUrlSource(
                url="https://www.youtube.com/watch?v=abc123",
                ack_rights=False,
                caller_id="builder",
            )
        )


def test_validate_remote_source_rejects_non_allowlisted_host():
    with pytest.raises(UnsupportedSourceError):
        validate_remote_source(
            RemoteUrlSource(
                url="https://vimeo.com/123456",
                ack_rights=True,
                caller_id="builder",
            )
        )


def test_download_public_video_raises_auth_required(monkeypatch):
    monkeypatch.setattr("sva.ingest.url_download.shutil.which", lambda name: "/usr/bin/yt-dlp")

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0],
            1,
            stdout="",
            stderr="Sign in to confirm you are not a bot",
        )

    monkeypatch.setattr("sva.ingest.url_download.subprocess.run", _fake_run)

    with pytest.raises(PublicUrlAuthenticationRequiredError):
        download_public_video(
            "https://www.youtube.com/watch?v=abc123",
            game_id="game_auth_required",
        )


def test_download_public_video_returns_created_file(monkeypatch, tmp_path):
    monkeypatch.setattr("sva.ingest.url_download.DOWNLOAD_DIR", tmp_path)
    monkeypatch.setattr("sva.ingest.url_download.shutil.which", lambda name: "/usr/bin/yt-dlp")

    def _fake_run(*args, **kwargs):
        created = tmp_path / "game_ok_demo.mp4"
        created.write_bytes(b"video")
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr("sva.ingest.url_download.subprocess.run", _fake_run)

    path = download_public_video(
        "https://www.youtube.com/watch?v=demo",
        game_id="game_ok",
    )

    assert path == tmp_path / "game_ok_demo.mp4"
    assert path.exists()


def test_local_file_source_is_explicit():
    source = LocalFileSource(path=str(Path("tests/fixtures/cfr_baseline.mp4")))
    assert source.path.endswith("cfr_baseline.mp4")
    assert DOWNLOAD_DIR.name == "downloads"


def test_validate_local_source_rejects_unsupported_extension():
    with pytest.raises(UnsupportedSourceError):
        validate_local_source(LocalFileSource(path="tests/fixtures/video.avi"))
