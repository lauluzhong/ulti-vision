"""Memory record persistence helpers for Phase 5."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
from sva.models import MemoryRecord, MemorySource


class MemoryRecordRow(Base):
    """ORM mapping for canonical memory records."""

    __tablename__ = "memory_records"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    memory_id = Column(Text, nullable=False, unique=True)
    kind = Column(Text, nullable=False, index=True)
    tags = Column(JSONB, nullable=False, server_default="[]")
    scope = Column(Text, nullable=False, index=True)
    source = Column(JSONB, nullable=False, server_default="{}")
    embedding_ref = Column(Text, nullable=True)
    embedding_input = Column(Text, nullable=False, server_default="")
    payload = Column(JSONB, nullable=False, server_default="{}")
    confidence = Column(Numeric(4, 3), nullable=False, server_default="0")
    corroborations = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)


def _to_memory_record(row: MemoryRecordRow) -> MemoryRecord:
    return MemoryRecord(
        memory_id=row.memory_id,
        kind=row.kind,
        tags=list(row.tags or []),
        scope=row.scope,
        source=MemorySource.model_validate(row.source or {}),
        embedding_ref=row.embedding_ref,
        embedding_input=row.embedding_input,
        payload=dict(row.payload or {}),
        confidence=float(row.confidence),
        corroborations=int(row.corroborations),
        created_at=row.created_at if isinstance(row.created_at, datetime) else datetime.fromisoformat(str(row.created_at)),
        last_used_at=row.last_used_at,
    )


def insert_memory_records(records: list[MemoryRecord]) -> None:
    """Persist canonical memory rows."""
    if not records:
        return
    with session_scope() as session:
        session.add_all(
            [
                MemoryRecordRow(
                    memory_id=record.memory_id,
                    kind=record.kind,
                    tags=record.tags,
                    scope=record.scope,
                    source=record.source.model_dump(mode="json"),
                    embedding_ref=record.embedding_ref,
                    embedding_input=record.embedding_input,
                    payload=record.payload,
                    confidence=record.confidence,
                    corroborations=record.corroborations,
                    created_at=record.created_at,
                    last_used_at=record.last_used_at,
                )
                for record in records
            ]
        )


def list_memory_records(
    *,
    scopes: list[str] | None = None,
    kinds: list[str] | None = None,
    tag: str | None = None,
    limit: int | None = None,
) -> list[MemoryRecord]:
    with session_scope() as session:
        stmt = select(MemoryRecordRow)
        if scopes:
            stmt = stmt.where(MemoryRecordRow.scope.in_(scopes))
        if kinds:
            stmt = stmt.where(MemoryRecordRow.kind.in_(kinds))
        if tag is not None:
            stmt = stmt.where(MemoryRecordRow.tags.contains([tag]))
        stmt = stmt.order_by(MemoryRecordRow.created_at.desc(), MemoryRecordRow.memory_id.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = session.execute(stmt).scalars()
        return [_to_memory_record(row) for row in rows]


__all__ = ["MemoryRecordRow", "insert_memory_records", "list_memory_records"]
