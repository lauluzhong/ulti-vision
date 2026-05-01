"""DB-gated tests for Phase 5 correction persistence."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from sva.models import CorrectionRecord

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
def test_insert_and_filter_corrections(migrated_db):
    from sva.db import get_engine
    from sva.memory.corrections_dao import insert_corrections, list_corrections

    game_id = "phase5_corrections_test"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM corrections WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text(
                "INSERT INTO jobs (game_id, video_id, status, source_path, source_kind, duration_s) "
                "VALUES (:g, :v, 'complete', :p, 'local_file', 90.0)"
            ),
            {"g": game_id, "v": "vid_phase5_corr", "p": "tests/fixtures/cfr_baseline.mp4"},
        )

    insert_corrections(
        [
            CorrectionRecord(
                correction_id="corr_phase5_001",
                game_id=game_id,
                point_id=f"{game_id}:pt_001",
                point_ordinal=1,
                source_event_id="evt_phase5_001",
                coach_id="coach_1",
                correction_type="reclassify",
                original_event={"type": "turnover", "team": "light"},
                proposed_event={"type": "completion", "team": "dark"},
                source_memory_refs=["mem_phase5_rule"],
                note="disc never hit ground",
                created_at=datetime.now(timezone.utc),
            )
        ]
    )

    coach_rows = list_corrections(game_id=game_id, coach_id="coach_1")
    assert len(coach_rows) == 1
    assert coach_rows[0].correction_id == "corr_phase5_001"
    assert coach_rows[0].original_event["type"] == "turnover"
    assert coach_rows[0].proposed_event["type"] == "completion"
    assert coach_rows[0].source_memory_refs == ["mem_phase5_rule"]

    source_rows = list_corrections(source_event_id="evt_phase5_001")
    assert len(source_rows) == 1
    assert source_rows[0].coach_id == "coach_1"

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM corrections WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
