"""DB-gated tests for Phase 2 point persistence."""

from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import text

from sva.points.types import BoundarySignal, PointRecord

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
def test_insert_and_query_points(migrated_db):
    from sva.db import get_engine
    from sva.points.dao import find_point_for_video_ts, insert_points, list_points

    game_id = "phase2_points_test"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM points WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text(
                "INSERT INTO jobs (game_id, video_id, status, source_path, source_kind, duration_s) "
                "VALUES (:g, :v, 'ingested', :p, 'local_file', 90.0)"
            ),
            {"g": game_id, "v": "vid_points_test", "p": "tests/fixtures/cfr_baseline.mp4"},
        )

    insert_points(
        [
            PointRecord(
                point_id="phase2_points_test:pt_001",
                game_id=game_id,
                point_ordinal=1,
                start_video_ts_ms=0,
                end_video_ts_ms=15000,
                confidence=0.9,
                boundary_evidence=[
                    BoundarySignal(source="scoreboard", video_ts_ms=0, confidence=0.9),
                ],
            ),
            PointRecord(
                point_id="phase2_points_test:pt_002",
                game_id=game_id,
                point_ordinal=2,
                start_video_ts_ms=15001,
                end_video_ts_ms=30000,
                confidence=0.8,
                boundary_evidence=[
                    BoundarySignal(source="pull", video_ts_ms=15100, confidence=0.8),
                ],
            ),
        ]
    )

    points = list_points(game_id)
    assert [point.point_ordinal for point in points] == [1, 2]

    owner = find_point_for_video_ts(game_id, 16000)
    assert owner is not None
    assert owner.point_id == "phase2_points_test:pt_002"

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM points WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
