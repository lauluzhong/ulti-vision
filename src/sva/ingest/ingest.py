"""End-to-end ingest: probe -> transcode to CFR -> persist jobs row.

Satisfies INGEST-03 (CFR transcode), INGEST-04 (VFR detection + normalization),
INGEST-05 (metadata persistence to jobs table).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Column, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
from sva.ingest.probe import VideoMetadata, probe_metadata
from sva.ingest.sampler import window_offsets
from sva.ingest.transcode import transcode_to_cfr

TRANSCODED_DIR = Path("data/transcoded")


class JobRow(Base):
    """ORM mapping for the jobs table created by migration 0001_phase1_foundation."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    game_id = Column(Text, nullable=False, unique=True, index=True)
    video_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    cost_usd = Column(Numeric(12, 6), nullable=False, server_default="0")
    source_path = Column(Text, nullable=True)
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


def _generate_game_id() -> str:
    return f"game_{uuid.uuid4().hex[:8]}"


def _generate_video_id() -> str:
    return f"vid_{uuid.uuid4().hex[:12]}"


def ingest_clip(
    path: Path | str,
    game_id: str | None = None,
    *,
    target_fps: int = 1,
) -> IngestResult:
    """Ingest one local video clip.

    Steps:
        1. Probe source metadata.
        2. Transcode to CFR H.264 mp4 at ``target_fps`` fps (INGEST-03).
        3. Persist a ``jobs`` row (INGEST-05).
        4. Compute window offsets for downstream perceive.
    """
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Source video not found: {src}")

    effective_game_id = game_id or _generate_game_id()
    video_id = _generate_video_id()

    src_meta = probe_metadata(src)

    TRANSCODED_DIR.mkdir(parents=True, exist_ok=True)
    transcoded_path = TRANSCODED_DIR / f"{video_id}.mp4"
    out_meta = transcode_to_cfr(src, transcoded_path, fps=target_fps)

    windows = window_offsets(out_meta.duration_s, fps=target_fps, window_size_s=2.0)

    with session_scope() as session:
        row = JobRow(
            game_id=effective_game_id,
            video_id=video_id,
            status="ingested",
            source_path=str(src.resolve()),
            duration_s=out_meta.duration_s,
        )
        session.add(row)

    return IngestResult(
        video_id=video_id,
        game_id=effective_game_id,
        source_path=str(src.resolve()),
        transcoded_path=str(transcoded_path.resolve()),
        duration_s=out_meta.duration_s,
        status="ingested",
        windows=windows,
        source_metadata=src_meta,
        transcoded_metadata=out_meta,
    )


__all__ = ["ingest_clip", "IngestResult", "JobRow", "TRANSCODED_DIR"]
