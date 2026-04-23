"""DB-gated tests for point-scoped event persistence."""

from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import text

from sva.models import Event, ModelMetadata


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
def test_insert_event_persists_point_scope_and_filters_by_point_id(migrated_db):
    from sva.db import get_engine
    from sva.events_dao import insert_event, list_event_rows_for_point

    game_id = "phase2_events_test"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text(
                "INSERT INTO jobs (game_id, video_id, status, source_path, source_kind, duration_s) "
                "VALUES (:g, :v, 'ingested', :p, 'local_file', 90.0)"
            ),
            {"g": game_id, "v": "vid_events_test", "p": "tests/fixtures/cfr_baseline.mp4"},
        )

    insert_event(
        Event(
            event_id="evt_phase2_001",
            game_id=game_id,
            point_id=f"{game_id}:pt_001",
            point_ordinal=1,
            video_ts_ms=1000,
            in_point_ts_ms=1000,
            type="completion",
            team="dark",
            model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
        )
    )
    insert_event(
        Event(
            event_id="evt_phase2_002",
            game_id=game_id,
            point_id=f"{game_id}:pt_002",
            point_ordinal=2,
            video_ts_ms=22000,
            in_point_ts_ms=500,
            type="turnover",
            team="light",
            model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
        )
    )

    point_one_rows = list_event_rows_for_point(game_id, f"{game_id}:pt_001")
    assert len(point_one_rows) == 1
    assert point_one_rows[0].point_id == f"{game_id}:pt_001"
    assert point_one_rows[0].point_ordinal == 1
    assert int(point_one_rows[0].in_point_ts_ms) == 1000

    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT point_id, point_ordinal, in_point_ts_ms "
                "FROM events WHERE game_id = :g AND point_id = :p ORDER BY video_ts_ms"
            ),
            {"g": game_id, "p": f"{game_id}:pt_002"},
        ).fetchall()

    assert len(rows) == 1
    assert rows[0].point_id == f"{game_id}:pt_002"
    assert rows[0].point_ordinal == 2
    assert int(rows[0].in_point_ts_ms) == 500

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
