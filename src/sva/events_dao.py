"""Events table DAO — one-row-per-Event insert via SQLAlchemy ORM."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID

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
    turnover_subtype = Column(Text, nullable=True)
    throw_type = Column(Text, nullable=True)
    pass_direction = Column(Text, nullable=True)
    prompt_version_hash = Column(Text, nullable=True)
    details = Column(JSONB, nullable=False, server_default="{}")
    schema_version = Column(Text, nullable=False, server_default="1.0")
    source_observations = Column(JSONB, nullable=False, server_default="[]")
    rule_refs = Column(JSONB, nullable=False, server_default="[]")
    memory_refs = Column(JSONB, nullable=False, server_default="[]")
    confidence = Column(Numeric(4, 3), nullable=True)
    warnings = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _event_row_from_event(event: Event) -> EventRow:
    return EventRow(
        event_id=event.event_id,
        game_id=event.game_id,
        point_id=event.point_id,
        point_ordinal=event.point_ordinal,
        video_ts_ms=event.video_ts_ms,
        in_point_ts_ms=event.in_point_ts_ms,
        type=event.type,
        team=event.team,
        turnover_subtype=event.turnover_subtype,
        throw_type=event.throw_type,
        pass_direction=event.pass_direction,
        prompt_version_hash=event.prompt_version_hash,
        details=event.details,
        schema_version=event.schema_version,
        source_observations=event.source_observations,
        rule_refs=event.rule_refs,
        memory_refs=event.memory_refs,
        confidence=event.confidence,
        warnings=event.warnings,
    )


def insert_event(event: Event) -> None:
    """Write one Event as an events row."""
    with session_scope() as session:
        session.add(_event_row_from_event(event))


def insert_events(events: list[Event]) -> None:
    """Write canonical Event rows in deterministic order."""
    if not events:
        return
    with session_scope() as session:
        session.add_all([_event_row_from_event(event) for event in events])


def list_event_rows(
    game_id: str,
    *,
    point_id: str | None = None,
    event_type: str | None = None,
    team: str | None = None,
) -> list[EventRow]:
    with session_scope() as session:
        stmt = select(EventRow).where(EventRow.game_id == game_id)
        if point_id is not None:
            stmt = stmt.where(EventRow.point_id == point_id)
        if event_type is not None:
            stmt = stmt.where(EventRow.type == event_type)
        if team is not None:
            stmt = stmt.where(EventRow.team == team)
        return list(
            session.execute(
                stmt.order_by(EventRow.video_ts_ms.asc(), EventRow.event_id.asc())
            ).scalars()
        )


def list_event_rows_for_point(game_id: str, point_id: str) -> list[EventRow]:
    return list_event_rows(game_id, point_id=point_id)


def derive_pass_count_for_point(game_id: str, point_id: str) -> int:
    with session_scope() as session:
        count = session.execute(
            select(func.count())
            .select_from(EventRow)
            .where(
                EventRow.game_id == game_id,
                EventRow.point_id == point_id,
                EventRow.type == "completion",
            )
        ).scalar_one()
    return int(count)


__all__ = [
    "EventRow",
    "insert_event",
    "insert_events",
    "list_event_rows",
    "list_event_rows_for_point",
    "derive_pass_count_for_point",
]
