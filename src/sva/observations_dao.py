"""Observation persistence helpers for Phase 3 cache-backed perception."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
from sva.models import Observation


class ObservationRow(Base):
    """ORM mapping for persisted Observation payloads."""

    __tablename__ = "observations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    observation_id = Column(Text, nullable=False, unique=True)
    game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
    point_id = Column(Text, nullable=False, index=True)
    point_ordinal = Column(Integer, nullable=False)
    video_id = Column(Text, nullable=False, index=True)
    window_id = Column(Text, nullable=False, index=True)
    prompt_version_hash = Column(Text, nullable=False, index=True)
    video_ts_start_ms = Column(BigInteger, nullable=False)
    video_ts_end_ms = Column(BigInteger, nullable=False)
    observation_ts_ms = Column(BigInteger, nullable=False)
    confidence_overall = Column(Numeric(4, 3), nullable=False)
    schema_version = Column(Text, nullable=False, server_default="1.0")
    raw_response_ref = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, server_default="{}")
    cache_hit = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def insert_observations(
    *,
    game_id: str,
    point_id: str,
    point_ordinal: int,
    prompt_version_hash: str,
    observations: list[Observation],
    cache_hit: bool = False,
) -> None:
    """Persist canonical Observation payloads for one cache key."""
    with session_scope() as session:
        session.add_all(
            [
                ObservationRow(
                    observation_id=observation.observation_id,
                    game_id=game_id,
                    point_id=point_id,
                    point_ordinal=point_ordinal,
                    video_id=observation.video_id,
                    window_id=observation.window_id,
                    prompt_version_hash=prompt_version_hash,
                    video_ts_start_ms=observation.video_ts_start_ms,
                    video_ts_end_ms=observation.video_ts_end_ms,
                    observation_ts_ms=observation.observation_ts_ms,
                    confidence_overall=observation.confidence_overall,
                    schema_version=observation.schema_version,
                    raw_response_ref=observation.raw_response_ref,
                    payload=observation.model_dump(mode="json"),
                    cache_hit=cache_hit,
                )
                for observation in observations
            ]
        )


def list_cached_observations(
    *,
    video_id: str,
    window_id: str,
    prompt_version_hash: str,
) -> list[Observation]:
    """Return persisted Observation rows for the exact cache-key triple."""
    with session_scope() as session:
        rows = session.execute(
            select(ObservationRow)
            .where(
                ObservationRow.video_id == video_id,
                ObservationRow.window_id == window_id,
                ObservationRow.prompt_version_hash == prompt_version_hash,
            )
            .order_by(ObservationRow.observation_ts_ms.asc(), ObservationRow.observation_id.asc())
        ).scalars()
        return [Observation.model_validate(row.payload) for row in rows]


__all__ = ["ObservationRow", "insert_observations", "list_cached_observations"]
