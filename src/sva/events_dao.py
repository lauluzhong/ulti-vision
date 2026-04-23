"""Events table DAO — one-row-per-Event insert via SQLAlchemy ORM."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
from sva.models import Event


class EventRow(Base):
    """ORM mapping for the events table (migration 0001_phase1_foundation)."""

    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    event_id = Column(Text, nullable=False, unique=True)
    game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
    point_id = Column(Text, nullable=False, index=True)
    point_ordinal = Column(Integer, nullable=False)
    video_ts_ms = Column(BigInteger, nullable=False)
    in_point_ts_ms = Column(BigInteger, nullable=False)
    type = Column(Text, nullable=False, index=True)
    team = Column(Text, nullable=False)
    details = Column(JSONB, nullable=False, server_default="{}")
    schema_version = Column(Text, nullable=False, server_default="1.0")
    source_observations = Column(JSONB, nullable=False, server_default="[]")
    memory_refs = Column(JSONB, nullable=False, server_default="[]")
    confidence = Column(Numeric(4, 3), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def insert_event(event: Event) -> None:
    """Write one Event as an events row."""
    with session_scope() as session:
        row = EventRow(
            event_id=event.event_id,
            game_id=event.game_id,
            point_id=event.point_id,
            point_ordinal=event.point_ordinal,
            video_ts_ms=event.video_ts_ms,
            in_point_ts_ms=event.in_point_ts_ms,
            type=event.type,
            team=event.team,
            details=event.details,
            schema_version=event.schema_version,
            source_observations=event.source_observations,
            memory_refs=event.memory_refs,
            confidence=event.confidence,
        )
        session.add(row)


def list_event_rows_for_point(game_id: str, point_id: str) -> list[EventRow]:
    with session_scope() as session:
        return list(
            session.execute(
                select(EventRow)
                .where(EventRow.game_id == game_id, EventRow.point_id == point_id)
                .order_by(EventRow.video_ts_ms.asc())
            ).scalars()
        )


__all__ = ["EventRow", "insert_event", "list_event_rows_for_point"]
