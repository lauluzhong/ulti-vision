"""DB-gated tests for Phase 5 memory record persistence."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from sva.models import MemoryRecord, MemorySource


def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def migrated_db():
    if not _db_reachable():
        pytest.skip("Postgres not reachable; start with `docker compose up -d db`")
    env = os.environ.copy()
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    yield


@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
def test_insert_and_filter_memory_records(migrated_db):
    from sva.db import get_engine
    from sva.memory.records_dao import insert_memory_records, list_memory_records

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM memory_records WHERE memory_id LIKE 'mem_phase5_%'"))

    insert_memory_records(
        [
            MemoryRecord(
                memory_id="mem_phase5_rule",
                kind="rule",
                tags=["turnover", "usau"],
                scope="global",
                source=MemorySource(origin="seed"),
                embedding_input="USAU turnover rule",
                payload={"rule_ref": "USAU-13"},
                created_at=datetime.now(timezone.utc),
            ),
            MemoryRecord(
                memory_id="mem_phase5_coach",
                kind="correction",
                tags=["completion", "sideline"],
                scope="coach:coach_1",
                source=MemorySource(origin="correction", source_coach_id="coach_1", source_correction_id="corr_1"),
                embedding_input="Completion near sideline should stay dark",
                payload={"event_type": "completion"},
                corroborations=1,
                created_at=datetime.now(timezone.utc),
            ),
        ]
    )

    global_rules = list_memory_records(scopes=["global"], kinds=["rule"])
    assert len(global_rules) == 1
    assert global_rules[0].memory_id == "mem_phase5_rule"
    assert global_rules[0].payload["rule_ref"] == "USAU-13"

    tagged = list_memory_records(scopes=["coach:coach_1"], tag="sideline")
    assert len(tagged) == 1
    assert tagged[0].memory_id == "mem_phase5_coach"
    assert tagged[0].source.source_coach_id == "coach_1"

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM memory_records WHERE memory_id LIKE 'mem_phase5_%'"))
