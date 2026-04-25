"""Correction-to-memory derivation and promotion gating for Phase 5."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sva.eval.gate import assert_memory_promotion_gate
from sva.eval.harness import EvalReport
from sva.models import CorrectionRecord, MemoryRecord, MemorySource


def _unique_tags(correction: CorrectionRecord) -> list[str]:
    tags: list[str] = [correction.correction_type]
    for payload in [correction.original_event, correction.proposed_event]:
        event_type = payload.get("type")
        if isinstance(event_type, str) and event_type not in tags:
            tags.append(event_type)
    return tags


def _embedding_input(correction: CorrectionRecord) -> str:
    original_type = correction.original_event.get("type", "unknown")
    proposed_type = correction.proposed_event.get("type", "unknown")
    base = (
        f"coach correction {correction.correction_type} for point {correction.point_id}: "
        f"original={original_type} proposed={proposed_type}"
    )
    if correction.note:
        return f"{base}. note={correction.note}"
    return base


def correction_to_memory_records(
    correction: CorrectionRecord,
    *,
    created_at: datetime | None = None,
) -> list[MemoryRecord]:
    """Turn one immutable correction into coach-scoped memory record(s)."""
    timestamp = created_at or correction.created_at or datetime.now(timezone.utc)
    return [
        MemoryRecord(
            memory_id=f"mem_{uuid4().hex[:12]}",
            kind="correction",
            tags=_unique_tags(correction),
            scope=f"coach:{correction.coach_id}",
            source=MemorySource(
                origin="correction",
                source_coach_id=correction.coach_id,
                source_correction_id=correction.correction_id,
                source_event_id=correction.source_event_id,
            ),
            embedding_input=_embedding_input(correction),
            payload={
                "correction_type": correction.correction_type,
                "original_event": correction.original_event,
                "proposed_event": correction.proposed_event,
                "source_memory_refs": correction.source_memory_refs,
                "note": correction.note,
                "point_id": correction.point_id,
                "point_ordinal": correction.point_ordinal,
            },
            created_at=timestamp,
        )
    ]


def can_promote_global(
    corroborating_corrections: list[CorrectionRecord],
    *,
    builder_curated: bool,
    min_distinct_coaches: int = 2,
) -> bool:
    """Return whether a memory pattern may become globally applied."""
    distinct_coaches = {
        correction.coach_id
        for correction in corroborating_corrections
        if correction.coach_id.strip()
    }
    return builder_curated and len(distinct_coaches) >= min_distinct_coaches


def promote_memory_record(
    record: MemoryRecord,
    corroborating_corrections: list[CorrectionRecord],
    *,
    builder_curated: bool,
    baseline_eval_report: EvalReport,
    candidate_eval_report: EvalReport,
    min_distinct_coaches: int = 2,
    created_at: datetime | None = None,
) -> MemoryRecord:
    """Create a new global memory record when the promotion gate passes."""
    if not can_promote_global(
        corroborating_corrections,
        builder_curated=builder_curated,
        min_distinct_coaches=min_distinct_coaches,
    ):
        raise ValueError("global promotion requires builder curation and corroboration from distinct coaches")
    assert_memory_promotion_gate(baseline_eval_report, candidate_eval_report)

    distinct_coaches = sorted({correction.coach_id for correction in corroborating_corrections})
    return record.model_copy(
        update={
            "memory_id": f"mem_{uuid4().hex[:12]}",
            "scope": "global",
            "corroborations": len(distinct_coaches),
            "created_at": created_at or datetime.now(timezone.utc),
            "source": MemorySource(
                origin=record.source.origin,
                source_correction_id=record.source.source_correction_id,
                source_event_id=record.source.source_event_id,
            ),
            "payload": {
                **record.payload,
                "promoted_from_memory_id": record.memory_id,
                "promoted_by_distinct_coaches": distinct_coaches,
                "promotion_eval_dataset_id": candidate_eval_report.dataset_id,
            },
        }
    )


__all__ = [
    "correction_to_memory_records",
    "can_promote_global",
    "promote_memory_record",
]
