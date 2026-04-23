"""DB-gated tests for Phase 3 observation persistence."""

from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import text

from sva.models import ModelMetadata, Observation


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
def test_insert_and_lookup_observations_by_cache_key(migrated_db):
    from sva.db import get_engine
    from sva.observations_dao import insert_observations, list_cached_observations

    game_id = "phase3_observations_test"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM observations WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text(
                "INSERT INTO jobs (game_id, video_id, status, source_path, source_kind, duration_s) "
                "VALUES (:g, :v, 'streaming', :p, 'local_file', 90.0)"
            ),
            {"g": game_id, "v": "vid_obs_test", "p": "tests/fixtures/cfr_baseline.mp4"},
        )

    observations = [
        Observation(
            observation_id="obs_phase3_001",
            window_id="win_phase3_001",
            video_id="vid_obs_test",
            video_ts_start_ms=0,
            video_ts_end_ms=2000,
            observation_ts_ms=1000,
            model=ModelMetadata(provider="dummy", model_id="dummy-vlm", version="test"),
            confidence_overall=0.5,
        ),
        Observation(
            observation_id="obs_phase3_002",
            window_id="win_phase3_001",
            video_id="vid_obs_test",
            video_ts_start_ms=0,
            video_ts_end_ms=2000,
            observation_ts_ms=1500,
            model=ModelMetadata(provider="dummy", model_id="dummy-vlm", version="test"),
            confidence_overall=0.7,
        ),
    ]

    insert_observations(
        game_id=game_id,
        point_id=f"{game_id}:pt_001",
        point_ordinal=1,
        prompt_version_hash="abc123def456",
        observations=observations,
    )

    cached = list_cached_observations(
        video_id="vid_obs_test",
        window_id="win_phase3_001",
        prompt_version_hash="abc123def456",
    )
    assert [obs.observation_id for obs in cached] == ["obs_phase3_001", "obs_phase3_002"]
    assert cached[0].disc.visibility_quality == "absent"
    assert cached[0].scene.multiple_discs_possible is False

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM observations WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
