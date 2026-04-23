"""Point persistence layer for Phase 2."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope
from sva.points.types import BoundarySignal, PointRecord


class PointRow(Base):
    """ORM mapping for the points table."""

    __tablename__ = "points"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    point_id = Column(Text, nullable=False, unique=True)
    game_id = Column(Text, ForeignKey("jobs.game_id", ondelete="CASCADE"), nullable=False, index=True)
    point_ordinal = Column(Integer, nullable=False)
    start_video_ts_ms = Column(BigInteger, nullable=False)
    end_video_ts_ms = Column(BigInteger, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False)
    boundary_evidence = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def insert_points(points: list[PointRecord]) -> None:
    with session_scope() as session:
        session.add_all(
            [
                PointRow(
                    point_id=point.point_id,
                    game_id=point.game_id,
                    point_ordinal=point.point_ordinal,
                    start_video_ts_ms=point.start_video_ts_ms,
                    end_video_ts_ms=point.end_video_ts_ms,
                    confidence=point.confidence,
                    boundary_evidence=[signal.model_dump() for signal in point.boundary_evidence],
                )
                for point in points
            ]
        )


def list_points(game_id: str) -> list[PointRecord]:
    with session_scope() as session:
        rows = session.execute(
            select(PointRow)
            .where(PointRow.game_id == game_id)
            .order_by(PointRow.point_ordinal.asc())
        ).scalars()
        return [
            PointRecord(
                point_id=row.point_id,
                game_id=row.game_id,
                point_ordinal=row.point_ordinal,
                start_video_ts_ms=row.start_video_ts_ms,
                end_video_ts_ms=row.end_video_ts_ms,
                confidence=float(row.confidence),
                boundary_evidence=[BoundarySignal.model_validate(signal) for signal in row.boundary_evidence],
            )
            for row in rows
        ]


def find_point_for_video_ts(game_id: str, video_ts_ms: int) -> PointRecord | None:
    with session_scope() as session:
        row = session.execute(
            select(PointRow).where(
                PointRow.game_id == game_id,
                PointRow.start_video_ts_ms <= video_ts_ms,
                PointRow.end_video_ts_ms >= video_ts_ms,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return PointRecord(
            point_id=row.point_id,
            game_id=row.game_id,
            point_ordinal=row.point_ordinal,
            start_video_ts_ms=row.start_video_ts_ms,
            end_video_ts_ms=row.end_video_ts_ms,
            confidence=float(row.confidence),
            boundary_evidence=[BoundarySignal.model_validate(signal) for signal in row.boundary_evidence],
        )


__all__ = ["PointRow", "find_point_for_video_ts", "insert_points", "list_points"]
