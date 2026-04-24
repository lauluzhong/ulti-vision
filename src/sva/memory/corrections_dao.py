"""Immutable coach correction persistence helpers for Phase 5."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
from sva.models import CorrectionRecord


class CorrectionRow(Base):
    """ORM mapping for immutable coach corrections."""

    __tablename__ = "corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    correction_id = Column(Text, nullable=False, unique=True)
    game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
    point_id = Column(Text, nullable=False, index=True)
    point_ordinal = Column(Integer, nullable=False)
    source_event_id = Column(Text, nullable=True, index=True)
    coach_id = Column(Text, nullable=False, index=True)
    correction_type = Column(Text, nullable=False, index=True)
    original_event = Column(JSONB, nullable=False, server_default="{}")
    proposed_event = Column(JSONB, nullable=False, server_default="{}")
    source_memory_refs = Column(JSONB, nullable=False, server_default="[]")
    note = Column(Text, nullable=False, server_default="")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _to_correction_record(row: CorrectionRow) -> CorrectionRecord:
    return CorrectionRecord(
        correction_id=row.correction_id,
        game_id=row.game_id,
        point_id=row.point_id,
        point_ordinal=int(row.point_ordinal),
        source_event_id=row.source_event_id,
        coach_id=row.coach_id,
        correction_type=row.correction_type,
        original_event=dict(row.original_event or {}),
        proposed_event=dict(row.proposed_event or {}),
        source_memory_refs=list(row.source_memory_refs or []),
        note=row.note,
        created_at=row.created_at if isinstance(row.created_at, datetime) else datetime.fromisoformat(str(row.created_at)),
    )


def insert_corrections(records: list[CorrectionRecord]) -> None:
    """Persist immutable correction rows."""
    if not records:
        return
    with session_scope() as session:
        session.add_all(
            [
                CorrectionRow(
                    correction_id=record.correction_id,
                    game_id=record.game_id,
                    point_id=record.point_id,
                    point_ordinal=record.point_ordinal,
                    source_event_id=record.source_event_id,
                    coach_id=record.coach_id,
                    correction_type=record.correction_type,
                    original_event=record.original_event,
                    proposed_event=record.proposed_event,
                    source_memory_refs=record.source_memory_refs,
                    note=record.note,
                    created_at=record.created_at,
                )
                for record in records
            ]
        )


def list_corrections(
    *,
    game_id: str | None = None,
    coach_id: str | None = None,
    source_event_id: str | None = None,
    limit: int | None = None,
) -> list[CorrectionRecord]:
    with session_scope() as session:
        stmt = select(CorrectionRow)
        if game_id is not None:
            stmt = stmt.where(CorrectionRow.game_id == game_id)
        if coach_id is not None:
            stmt = stmt.where(CorrectionRow.coach_id == coach_id)
        if source_event_id is not None:
            stmt = stmt.where(CorrectionRow.source_event_id == source_event_id)
        stmt = stmt.order_by(CorrectionRow.created_at.desc(), CorrectionRow.correction_id.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).scalars()
        return [_to_correction_record(row) for row in rows]


__all__ = ["CorrectionRow", "insert_corrections", "list_corrections"]
