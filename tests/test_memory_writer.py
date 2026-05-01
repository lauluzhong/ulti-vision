"""Unit tests for Phase 5 correction writer and promotion gate."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sva.memory.writer import can_promote_global, correction_to_memory_records, promote_memory_record
from sva.eval.harness import AlphaGateStatus, EvalReport
from sva.eval.metrics import EventMetric
from sva.models import CorrectionRecord, MemoryRecord, MemorySource

def _correction(correction_id: str, coach_id: str) -> CorrectionRecord:
    return CorrectionRecord(
        correction_id=correction_id,
        game_id="game_1",
        point_id="game_1:pt_001",
        point_ordinal=1,
        source_event_id="evt_001",
        coach_id=coach_id,
        correction_type="reclassify",
        original_event={"type": "turnover", "team": "light"},
        proposed_event={"type": "completion", "team": "dark"},
        source_memory_refs=["mem_rule_1"],
        note="disc never hit ground",
        created_at=datetime.now(timezone.utc),
    )

def _eval_report(*, dataset_ready: bool = True, completion_recall: float = 0.97) -> EvalReport:
    return EvalReport(
        dataset_id="gold_v1",
        dataset_ready=dataset_ready,
        blocking_reasons=[] if dataset_ready else ["need real gold set"],
        full_games_total=3,
        points_total=40,
        independent_annotation_complete=dataset_ready,
        metrics_by_type={
            "completion": EventMetric(
                gold_count=10,
                predicted_count=10,
                true_positives=10,
                false_positives=0,
                false_negatives=0,
                precision=0.8,
                recall=completion_recall,
            )
        },
        alpha_gate=AlphaGateStatus(
            ready=dataset_ready,
            blocked_reasons=[] if dataset_ready else ["need real gold set"],
            completion_recall=completion_recall,
            completion_precision=0.8 if dataset_ready else None,
            goal_recall=1.0 if dataset_ready else None,
            possession_change_recall=0.95 if dataset_ready else None,
        ),
    )

def test_correction_to_memory_records_defaults_to_coach_scope():
    correction = _correction("corr_001", "coach_1")
    records = correction_to_memory_records(correction)

    assert len(records) == 1
    record = records[0]
    assert record.kind == "correction"
    assert record.scope == "coach:coach_1"
    assert record.source.source_coach_id == "coach_1"
    assert record.source.source_correction_id == "corr_001"
    assert record.source.source_event_id == "evt_001"
    assert "reclassify" in record.tags
    assert "turnover" in record.tags
    assert "completion" in record.tags
    assert "disc never hit ground" in record.embedding_input
    assert record.payload["source_memory_refs"] == ["mem_rule_1"]

def test_can_promote_global_requires_distinct_coaches_and_builder_curation():
    same_coach = [_correction("corr_001", "coach_1"), _correction("corr_002", "coach_1")]
    distinct = [_correction("corr_001", "coach_1"), _correction("corr_002", "coach_2")]

    assert can_promote_global(same_coach, builder_curated=True) is False
    assert can_promote_global(distinct, builder_curated=False) is False
    assert can_promote_global(distinct, builder_curated=True) is True

def test_promote_memory_record_creates_new_global_row():
    base = MemoryRecord(
        memory_id="mem_coach_only",
        kind="correction",
        tags=["reclassify", "completion"],
        scope="coach:coach_1",
        source=MemorySource(
            origin="correction",
            source_coach_id="coach_1",
            source_correction_id="corr_001",
            source_event_id="evt_001",
        ),
        embedding_input="coach correction",
        payload={"source_memory_refs": ["mem_rule_1"]},
        created_at=datetime.now(timezone.utc),
    )
    promoted = promote_memory_record(
        base,
        [_correction("corr_001", "coach_1"), _correction("corr_002", "coach_2")],
        builder_curated=True,
        baseline_eval_report=_eval_report(completion_recall=0.97),
        candidate_eval_report=_eval_report(completion_recall=0.96),
    )

    assert promoted.memory_id != "mem_coach_only"
    assert promoted.scope == "global"
    assert promoted.corroborations == 2
    assert promoted.payload["promoted_from_memory_id"] == "mem_coach_only"
    assert promoted.payload["promoted_by_distinct_coaches"] == ["coach_1", "coach_2"]
    assert promoted.payload["promotion_eval_dataset_id"] == "gold_v1"
    assert promoted.source.source_coach_id is None

def test_promote_memory_record_blocks_single_coach_loop():
    base = MemoryRecord(
        memory_id="mem_coach_only",
        kind="correction",
        tags=["reclassify"],
        scope="coach:coach_1",
        source=MemorySource(origin="correction", source_coach_id="coach_1"),
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError):
        promote_memory_record(
            base,
            [_correction("corr_001", "coach_1"), _correction("corr_002", "coach_1")],
            builder_curated=True,
            baseline_eval_report=_eval_report(completion_recall=0.97),
            candidate_eval_report=_eval_report(completion_recall=0.97),
        )

def test_promote_memory_record_blocks_when_eval_gate_fails():
    base = MemoryRecord(
        memory_id="mem_coach_only",
        kind="correction",
        tags=["reclassify"],
        scope="coach:coach_1",
        source=MemorySource(origin="correction", source_coach_id="coach_1"),
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError, match="completion recall dropped"):
        promote_memory_record(
            base,
            [_correction("corr_001", "coach_1"), _correction("corr_002", "coach_2")],
            builder_curated=True,
            baseline_eval_report=_eval_report(completion_recall=0.97),
            candidate_eval_report=_eval_report(completion_recall=0.94),
        )
