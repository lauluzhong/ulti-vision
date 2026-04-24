"""Job lifecycle persistence helpers for Phase 6 orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Column, DateTime, Numeric, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope


class JobRow(Base):
    """ORM mapping for the canonical jobs table."""

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    game_id = Column(Text, nullable=False, unique=True, index=True)
    video_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="pending")
    stage = Column(Text, nullable=False, server_default="queued")
    progress = Column(JSONB, nullable=False, server_default="{}")
    error_message = Column(Text, nullable=True)
    cost_usd = Column(Numeric(12, 6), nullable=False, server_default="0")
    source_path = Column(Text, nullable=True)
    source_kind = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    duration_s = Column(Numeric(10, 3), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


@dataclass(frozen=True, slots=True)
class JobRecord:
    game_id: str
    video_id: str | None
    status: str
    stage: str
    progress: dict[str, Any]
    error_message: str | None
    cost_usd: Decimal
    source_path: str | None
    source_kind: str | None
    source_url: str | None
    duration_s: float | None
    created_at: datetime
    updated_at: datetime


def _coerce_datetime(value: datetime | object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _to_job_record(row: JobRow) -> JobRecord:
    return JobRecord(
        game_id=row.game_id,
        video_id=row.video_id,
        status=row.status,
        stage=row.stage,
        progress=dict(row.progress or {}),
        error_message=row.error_message,
        cost_usd=Decimal(row.cost_usd),
        source_path=row.source_path,
        source_kind=row.source_kind,
        source_url=row.source_url,
        duration_s=float(row.duration_s) if row.duration_s is not None else None,
        created_at=_coerce_datetime(row.created_at),
        updated_at=_coerce_datetime(row.updated_at),
    )


def get_job(game_id: str) -> JobRecord | None:
    with session_scope() as session:
        row = session.execute(
            select(JobRow).where(JobRow.game_id == game_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return _to_job_record(row)


def upsert_job(
    *,
    game_id: str,
    video_id: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    progress: dict[str, Any] | None = None,
    error_message: str | None = None,
    source_path: str | None = None,
    source_kind: str | None = None,
    source_url: str | None = None,
    duration_s: float | None = None,
) -> JobRecord:
    with session_scope() as session:
        row = session.execute(
            select(JobRow).where(JobRow.game_id == game_id)
        ).scalar_one_or_none()
        if row is None:
            row = JobRow(
                game_id=game_id,
                video_id=video_id,
                status=status or "queued",
                stage=stage or "queued",
                progress=progress or {},
                error_message=error_message,
                source_path=source_path,
                source_kind=source_kind,
                source_url=source_url,
                duration_s=duration_s,
            )
            session.add(row)
            session.flush()
            return _to_job_record(row)

        if video_id is not None:
            row.video_id = video_id
        if status is not None:
            row.status = status
        if stage is not None:
            row.stage = stage
        if progress is not None:
            row.progress = progress
        if error_message is not None or error_message is None:
            row.error_message = error_message
        if source_path is not None:
            row.source_path = source_path
        if source_kind is not None:
            row.source_kind = source_kind
        if source_url is not None:
            row.source_url = source_url
        if duration_s is not None:
            row.duration_s = duration_s
        row.updated_at = func.now()
        session.flush()
        return _to_job_record(row)


__all__ = ["JobRecord", "JobRow", "get_job", "upsert_job"]
