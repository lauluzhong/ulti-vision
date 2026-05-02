"""End-to-end ingest: probe -> transcode to CFR -> persist jobs row.

Satisfies INGEST-03 (CFR transcode), INGEST-04 (VFR detection + normalization),
INGEST-05 (metadata persistence to jobs table).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from sva.ingest.probe import VideoMetadata, probe_metadata
from sva.ingest.sampler import window_offsets
from sva.ingest.sources import (
    LocalFileSource,
    RemoteUrlSource,
    log_rights_ack,
    validate_local_source,
    validate_remote_source,
)
from sva.ingest.transcode import transcode_to_cfr
from sva.ingest.url_download import download_public_video
from sva.jobs_dao import JobRow, get_job, upsert_job

TRANSCODED_DIR = Path("data/transcoded")
SourceInput: TypeAlias = LocalFileSource | RemoteUrlSource

# How many frames per second of source video the transcoded MP4 retains.
# This is DIFFERENT from `target_fps` (which is the sampling rate for
# window identity / cache key) and DIFFERENT from Gemini's
# video_metadata.fps (which controls in-window frame extraction).
#
# Why 5: at 1 fps the transcoded file only had ONE frame per source
# second, so even with video_metadata.fps=4 Gemini was looking at the
# same frame 4 times. 5 fps gives the VLM real frame variety for motion
# detection without bloating file size unnecessarily.
TRANSCODE_FPS = 5


@dataclass(frozen=True)
class IngestResult:
    video_id: str
    game_id: str
    source_path: str
    transcoded_path: str
    duration_s: float
    status: str
    windows: list[tuple[int, int]]
    source_metadata: VideoMetadata
    transcoded_metadata: VideoMetadata
    source_kind: str = "local_file"
    source_url: str | None = None


def _generate_game_id() -> str:
    return f"game_{uuid.uuid4().hex[:8]}"


def _generate_video_id() -> str:
    return f"vid_{uuid.uuid4().hex[:12]}"


def _ingest_resolved_path(
    src: Path,
    *,
    game_id: str,
    target_fps: int,
    source_kind: str,
    source_url: str | None = None,
) -> IngestResult:
    if not src.exists():
        raise FileNotFoundError(f"Source video not found: {src}")

    video_id = _generate_video_id()
    src_meta = probe_metadata(src)

    TRANSCODED_DIR.mkdir(parents=True, exist_ok=True)
    transcoded_path = TRANSCODED_DIR / f"{video_id}.mp4"
    # Transcode at TRANSCODE_FPS, NOT target_fps. The transcoded file is what
    # Gemini sees, so this is the maximum temporal resolution available to the
    # VLM. target_fps is only used for the sampler stride / window identity.
    out_meta = transcode_to_cfr(src, transcoded_path, fps=TRANSCODE_FPS)

    # v0: non-overlapping 2-sec windows. Each throw appears in exactly ONE window
    # so the LLM doesn't have to dedupe sliding-window overlap. stride_s=2.0
    # halves the Gemini call count vs the legacy fps=1 overlap mode.
    windows = window_offsets(
        out_meta.duration_s,
        fps=target_fps,
        window_size_s=2.0,
        stride_s=2.0,
    )

    upsert_job(
        game_id=game_id,
        video_id=video_id,
        status="ingested",
        stage="ingest_complete",
        progress={"target_fps": target_fps, "windows_total": len(windows)},
        error_message=None,
        source_path=str(src.resolve()),
        source_kind=source_kind,
        source_url=source_url,
        duration_s=out_meta.duration_s,
    )

    return IngestResult(
        video_id=video_id,
        game_id=game_id,
        source_path=str(src.resolve()),
        transcoded_path=str(transcoded_path.resolve()),
        duration_s=out_meta.duration_s,
        status="ingested",
        windows=windows,
        source_metadata=src_meta,
        transcoded_metadata=out_meta,
        source_kind=source_kind,
        source_url=source_url,
    )


def ingest_source(
    source: SourceInput,
    game_id: str | None = None,
    *,
    target_fps: int = 1,
) -> IngestResult:
    """Ingest a local file or approved public URL through one normalization path."""
    effective_game_id = game_id or _generate_game_id()

    if isinstance(source, RemoteUrlSource):
        source = validate_remote_source(source)
        log_rights_ack(
            game_id=effective_game_id,
            source_url=source.url,
            caller_id=source.caller_id,
        )
        downloaded_path = download_public_video(source.url, game_id=effective_game_id)
        return _ingest_resolved_path(
            downloaded_path,
            game_id=effective_game_id,
            target_fps=target_fps,
            source_kind="public_url",
            source_url=source.url,
        )

    validated_local = validate_local_source(source)
    return _ingest_resolved_path(
        Path(validated_local.path),
        game_id=effective_game_id,
        target_fps=target_fps,
        source_kind="local_file",
    )


def ingest_local_file(
    path: Path | str,
    game_id: str | None = None,
    *,
    target_fps: int = 1,
) -> IngestResult:
    return ingest_source(LocalFileSource(path=Path(path)), game_id=game_id, target_fps=target_fps)


def ingest_remote_url(
    url: str,
    *,
    caller_id: str,
    ack_rights: bool,
    game_id: str | None = None,
    target_fps: int = 1,
) -> IngestResult:
    return ingest_source(
        RemoteUrlSource(url=url, ack_rights=ack_rights, caller_id=caller_id),
        game_id=game_id,
        target_fps=target_fps,
    )


def ingest_clip(
    path: Path | str,
    game_id: str | None = None,
    *,
    target_fps: int = 1,
) -> IngestResult:
    """Backward-compatible alias for Phase 1 callers."""
    return ingest_local_file(path, game_id=game_id, target_fps=target_fps)


def load_ingest_result_for_job(
    game_id: str,
    *,
    target_fps: int | None = None,
) -> IngestResult:
    """Rebuild an ingest result from persisted job metadata for resume flows."""
    job = get_job(game_id)
    if job is None:
        raise ValueError(f"Unknown job/game_id: {game_id}")
    if not job.video_id:
        raise ValueError(f"Job {game_id} has no persisted video_id yet")
    if not job.source_path:
        raise ValueError(f"Job {game_id} has no persisted source_path")

    src = Path(job.source_path)
    transcoded_path = TRANSCODED_DIR / f"{job.video_id}.mp4"
    if not transcoded_path.exists():
        raise FileNotFoundError(f"Transcoded video not found for job {game_id}: {transcoded_path}")

    source_meta = probe_metadata(src)
    transcoded_meta = probe_metadata(transcoded_path)
    effective_fps = target_fps or int((job.progress or {}).get("target_fps", 1) or 1)
    windows = window_offsets(
        transcoded_meta.duration_s,
        fps=effective_fps,
        window_size_s=2.0,
        stride_s=2.0,
    )
    return IngestResult(
        video_id=job.video_id,
        game_id=job.game_id,
        source_path=str(src.resolve()),
        transcoded_path=str(transcoded_path.resolve()),
        duration_s=transcoded_meta.duration_s,
        status=job.status,
        windows=windows,
        source_metadata=source_meta,
        transcoded_metadata=transcoded_meta,
        source_kind=job.source_kind or "local_file",
        source_url=job.source_url,
    )


__all__ = [
    "SourceInput",
    "ingest_clip",
    "ingest_local_file",
    "ingest_remote_url",
    "ingest_source",
    "IngestResult",
    "JobRow",
    "load_ingest_result_for_job",
    "TRANSCODED_DIR",
]
