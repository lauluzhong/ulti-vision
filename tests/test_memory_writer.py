"""Unit tests for Phase 5 correction writer and promotion gate."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sva.memory.writer import can_promote_global, correction_to_memory_records, promote_memory_record
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
    )

    assert promoted.memory_id != "mem_coach_only"
    assert promoted.scope == "global"
    assert promoted.corroborations == 2
    assert promoted.payload["promoted_from_memory_id"] == "mem_coach_only"
    assert promoted.payload["promoted_by_distinct_coaches"] == ["coach_1", "coach_2"]
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
        )
