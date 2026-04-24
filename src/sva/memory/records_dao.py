"""Memory record persistence helpers for Phase 5."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ARRAY, Column, DateTime, Float, ForeignKey, Integer, Numeric, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
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


class MemoryEmbeddingRow(Base):
    """ORM mapping for persisted embedding payloads keyed by memory_id."""

    __tablename__ = "memory_embeddings"

    memory_id = Column(
        Text,
        ForeignKey("memory_records.memory_id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider = Column(Text, nullable=False)
    model_id = Column(Text, nullable=False)
    content_hash = Column(Text, nullable=False)
    dimensions = Column(Integer, nullable=False)
    vector = Column(ARRAY(Float(asdecimal=False)), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


@dataclass(slots=True)
class MemoryEmbeddingRecord:
    """Typed embedding payload returned to retriever code without extra packages."""

    memory_id: str
    provider: str
    model_id: str
    content_hash: str
    vector: list[float]
    dimensions: int
    created_at: datetime
    updated_at: datetime


def _coerce_datetime(value: datetime | object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


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
        created_at=_coerce_datetime(row.created_at),
        last_used_at=row.last_used_at,
    )


def _to_memory_embedding_record(row: MemoryEmbeddingRow) -> MemoryEmbeddingRecord:
    return MemoryEmbeddingRecord(
        memory_id=row.memory_id,
        provider=row.provider,
        model_id=row.model_id,
        content_hash=row.content_hash,
        vector=[float(value) for value in (row.vector or [])],
        dimensions=int(row.dimensions),
        created_at=_coerce_datetime(row.created_at),
        updated_at=_coerce_datetime(row.updated_at),
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


def upsert_memory_embedding(
    *,
    memory_id: str,
    provider: str,
    model_id: str,
    content_hash: str,
    vector: list[float],
) -> None:
    """Insert or replace a single embedding payload keyed by memory_id."""
    normalized_vector = [float(value) for value in vector]
    if not normalized_vector:
        raise ValueError(f"Embedding for memory_id={memory_id!r} must not be empty")

    stmt = insert(MemoryEmbeddingRow).values(
        memory_id=memory_id,
        provider=provider,
        model_id=model_id,
        content_hash=content_hash,
        dimensions=len(normalized_vector),
        vector=normalized_vector,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[MemoryEmbeddingRow.memory_id],
        set_={
            "provider": stmt.excluded.provider,
            "model_id": stmt.excluded.model_id,
            "content_hash": stmt.excluded.content_hash,
            "dimensions": stmt.excluded.dimensions,
            "vector": stmt.excluded.vector,
            "updated_at": func.now(),
        },
    )
    with session_scope() as session:
        session.execute(stmt)


def list_memory_embeddings(
    *,
    memory_ids: list[str],
    provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, MemoryEmbeddingRecord]:
    if not memory_ids:
        return {}
    with session_scope() as session:
        stmt = select(MemoryEmbeddingRow)
        stmt = stmt.where(MemoryEmbeddingRow.memory_id.in_(memory_ids))
        if provider is not None:
            stmt = stmt.where(MemoryEmbeddingRow.provider == provider)
        if model_id is not None:
            stmt = stmt.where(MemoryEmbeddingRow.model_id == model_id)
        stmt = stmt.order_by(
            MemoryEmbeddingRow.updated_at.desc(),
            MemoryEmbeddingRow.memory_id.asc(),
        )
        rows = session.execute(stmt).scalars()
        records = (_to_memory_embedding_record(row) for row in rows)
        return {record.memory_id: record for record in records}


__all__ = [
    "MemoryEmbeddingRecord",
    "MemoryEmbeddingRow",
    "MemoryRecordRow",
    "insert_memory_records",
    "list_memory_embeddings",
    "list_memory_records",
    "upsert_memory_embedding",
]
