"""End-to-end ingest: probe -> transcode to CFR -> persist jobs row.

Satisfies INGEST-03 (CFR transcode), INGEST-04 (VFR detection + normalization),
INGEST-05 (metadata persistence to jobs table).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from sqlalchemy import Column, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
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

TRANSCODED_DIR = Path("data/transcoded")
SourceInput: TypeAlias = LocalFileSource | RemoteUrlSource


class JobRow(Base):
    """ORM mapping for the jobs table created by migration 0001_phase1_foundation."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    game_id = Column(Text, nullable=False, unique=True, index=True)
    video_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    cost_usd = Column(Numeric(12, 6), nullable=False, server_default="0")
    source_path = Column(Text, nullable=True)
    source_kind = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    duration_s = Column(Numeric(10, 3), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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
    out_meta = transcode_to_cfr(src, transcoded_path, fps=target_fps)

    windows = window_offsets(out_meta.duration_s, fps=target_fps, window_size_s=2.0)

    with session_scope() as session:
        row = JobRow(
            game_id=game_id,
            video_id=video_id,
            status="ingested",
            source_path=str(src.resolve()),
            source_kind=source_kind,
            source_url=source_url,
            duration_s=out_meta.duration_s,
        )
        session.add(row)

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


__all__ = [
    "SourceInput",
    "ingest_clip",
    "ingest_local_file",
    "ingest_remote_url",
    "ingest_source",
    "IngestResult",
    "JobRow",
    "TRANSCODED_DIR",
]
