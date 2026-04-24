"""Thin correction orchestration over the Phase 5 memory substrate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sva.events_dao import list_event_rows
from sva.memory.corrections_dao import insert_corrections
from sva.memory.records_dao import insert_memory_records
from sva.memory.writer import correction_to_memory_records
from sva.models import CorrectionRecord


@dataclass(slots=True)
class CorrectionSubmission:
    point_id: str
    point_ordinal: int
    source_event_id: str | None
    coach_id: str
    correction_type: str
    original_event: dict[str, Any]
    proposed_event: dict[str, Any]
    source_memory_refs: list[str]
    note: str


@dataclass(slots=True)
class CorrectionSubmissionResult:
    correction_id: str
    game_id: str
    point_id: str
    point_ordinal: int
    coach_id: str
    correction_type: str
    created_memory_ids: list[str]


def _event_snapshot(row: Any) -> dict[str, Any]:
    return {
        "event_id": row.event_id,
        "type": row.type,
        "team": row.team,
        "point_id": row.point_id,
        "point_ordinal": int(row.point_ordinal),
        "video_ts_ms": int(row.video_ts_ms),
        "in_point_ts_ms": int(row.in_point_ts_ms),
        "turnover_subtype": row.turnover_subtype,
        "throw_type": row.throw_type,
        "pass_direction": row.pass_direction,
        "details": dict(row.details or {}),
        "rule_refs": list(row.rule_refs or []),
        "memory_refs": list(row.memory_refs or []),
    }


def submit_correction(game_id: str, payload: CorrectionSubmission) -> CorrectionSubmissionResult:
    coach_id = payload.coach_id.strip()
    if not coach_id:
        raise ValueError("coach_id must not be blank")

    source_event = None
    if payload.source_event_id is not None:
        point_events = list_event_rows(game_id, point_id=payload.point_id)
        source_event = next(
            (row for row in point_events if row.event_id == payload.source_event_id),
            None,
        )
        if source_event is None:
            raise FileNotFoundError(
                f"Unknown source event {payload.source_event_id!r} for game {game_id!r}"
            )
        if int(source_event.point_ordinal) != payload.point_ordinal:
            raise ValueError("source event point_ordinal does not match correction payload")

    original_event = payload.original_event
    source_memory_refs = payload.source_memory_refs
    if source_event is not None:
        original_event = _event_snapshot(source_event)
        source_memory_refs = list(source_event.memory_refs or [])

    correction = CorrectionRecord(
        correction_id=f"corr_{uuid4().hex[:12]}",
        game_id=game_id,
        point_id=payload.point_id,
        point_ordinal=payload.point_ordinal,
        source_event_id=payload.source_event_id,
        coach_id=coach_id,
        correction_type=payload.correction_type,
        original_event=original_event,
        proposed_event=payload.proposed_event,
        source_memory_refs=source_memory_refs,
        note=payload.note,
        created_at=datetime.now(timezone.utc),
    )
    insert_corrections([correction])

    derived_memory = correction_to_memory_records(correction)
    insert_memory_records(derived_memory)
    return CorrectionSubmissionResult(
        correction_id=correction.correction_id,
        game_id=game_id,
        point_id=correction.point_id,
        point_ordinal=correction.point_ordinal,
        coach_id=correction.coach_id,
        correction_type=correction.correction_type,
        created_memory_ids=[record.memory_id for record in derived_memory],
    )


__all__ = [
    "CorrectionSubmission",
    "CorrectionSubmissionResult",
    "submit_correction",
]
