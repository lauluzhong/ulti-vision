"""Point-boundary editing and rebucketing service for Phase 7."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select

from sva.db import session_scope
from sva.events_dao import EventRow
from sva.memory.corrections_dao import CorrectionRow
from sva.observations_dao import ObservationRow
from sva.points.dao import PointRow, list_points
from sva.points.types import BoundarySignal, PointRecord


@dataclass(frozen=True, slots=True)
class PointBoundaryPatch:
    start_video_ts_ms: int
    end_video_ts_ms: int


@dataclass(frozen=True, slots=True)
class PointBoundaryUpdateResult:
    game_id: str
    points: list[PointRecord]
    events_rebucketed: int
    observations_rebucketed: int


def _stable_point_id(game_id: str, point_ordinal: int) -> str:
    return f"{game_id}:pt_{point_ordinal:03d}"


def _manual_signal(start_video_ts_ms: int) -> BoundarySignal:
    return BoundarySignal(
        source="manual",
        video_ts_ms=start_video_ts_ms,
        confidence=1.0,
        details={"edited": True},
    )


def _build_replacement_points(game_id: str, patches: list[PointBoundaryPatch]) -> list[PointRecord]:
    if not patches:
        raise ValueError("at least one point boundary is required")

    points: list[PointRecord] = []
    previous_end: int | None = None
    for ordinal, patch in enumerate(patches, start=1):
        if patch.end_video_ts_ms < patch.start_video_ts_ms:
            raise ValueError("point boundary end_video_ts_ms must be >= start_video_ts_ms")
        if previous_end is not None and patch.start_video_ts_ms <= previous_end:
            raise ValueError("point boundaries must be ordered and non-overlapping")
        points.append(
            PointRecord(
                point_id=_stable_point_id(game_id, ordinal),
                game_id=game_id,
                point_ordinal=ordinal,
                start_video_ts_ms=patch.start_video_ts_ms,
                end_video_ts_ms=patch.end_video_ts_ms,
                confidence=1.0,
                boundary_evidence=[_manual_signal(patch.start_video_ts_ms)],
            )
        )
        previous_end = patch.end_video_ts_ms
    return points


def _find_owner(points: list[PointRecord], video_ts_ms: int) -> PointRecord | None:
    for point in points:
        if point.start_video_ts_ms <= video_ts_ms <= point.end_video_ts_ms:
            return point
    return None


def _rebucket_event_rows(rows: list[Any], points: list[PointRecord]) -> int:
    rebucketed = 0
    for row in rows:
        owner = _find_owner(points, int(row.video_ts_ms))
        if owner is None:
            raise ValueError(
                f"event {row.event_id!r} falls outside the edited point boundaries"
            )
        in_point_ts_ms = int(row.video_ts_ms) - owner.start_video_ts_ms
        if (
            row.point_id != owner.point_id
            or int(row.point_ordinal) != owner.point_ordinal
            or int(row.in_point_ts_ms) != in_point_ts_ms
        ):
            row.point_id = owner.point_id
            row.point_ordinal = owner.point_ordinal
            row.in_point_ts_ms = in_point_ts_ms
            rebucketed += 1
    return rebucketed


def _rebucket_observation_rows(rows: list[Any], points: list[PointRecord]) -> int:
    rebucketed = 0
    for row in rows:
        owner = _find_owner(points, int(row.observation_ts_ms))
        if owner is None:
            raise ValueError(
                f"observation {row.observation_id!r} falls outside the edited point boundaries"
            )
        if row.point_id != owner.point_id or int(row.point_ordinal) != owner.point_ordinal:
            row.point_id = owner.point_id
            row.point_ordinal = owner.point_ordinal
            rebucketed += 1
    return rebucketed


def list_point_boundaries(game_id: str) -> list[PointRecord]:
    return list_points(game_id)


def replace_point_boundaries(
    game_id: str,
    patches: list[PointBoundaryPatch],
) -> PointBoundaryUpdateResult:
    replacement_points = _build_replacement_points(game_id, patches)

    with session_scope() as session:
        existing_correction = session.execute(
            select(CorrectionRow.correction_id)
            .where(CorrectionRow.game_id == game_id)
            .limit(1)
        ).scalar_one_or_none()
        if existing_correction is not None:
            raise ValueError(
                "point boundaries cannot be edited after corrections exist for this game"
            )

        event_rows = list(
            session.execute(
                select(EventRow)
                .where(EventRow.game_id == game_id)
                .order_by(EventRow.video_ts_ms.asc(), EventRow.event_id.asc())
            ).scalars()
        )
        observation_rows = list(
            session.execute(
                select(ObservationRow)
                .where(ObservationRow.game_id == game_id)
                .order_by(
                    ObservationRow.observation_ts_ms.asc(),
                    ObservationRow.observation_id.asc(),
                )
            ).scalars()
        )

        events_rebucketed = _rebucket_event_rows(event_rows, replacement_points)
        observations_rebucketed = _rebucket_observation_rows(observation_rows, replacement_points)

        session.execute(delete(PointRow).where(PointRow.game_id == game_id))
        session.add_all(
            [
                PointRow(
                    point_id=point.point_id,
                    game_id=point.game_id,
                    point_ordinal=point.point_ordinal,
                    start_video_ts_ms=point.start_video_ts_ms,
                    end_video_ts_ms=point.end_video_ts_ms,
                    confidence=point.confidence,
                    boundary_evidence=[
                        signal.model_dump(mode="json") for signal in point.boundary_evidence
                    ],
                )
                for point in replacement_points
            ]
        )
        session.flush()

    return PointBoundaryUpdateResult(
        game_id=game_id,
        points=replacement_points,
        events_rebucketed=events_rebucketed,
        observations_rebucketed=observations_rebucketed,
    )


__all__ = [
    "PointBoundaryPatch",
    "PointBoundaryUpdateResult",
    "list_point_boundaries",
    "replace_point_boundaries",
]
