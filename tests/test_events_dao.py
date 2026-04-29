"""DB-gated tests for point-scoped event persistence and filtering."""

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
def test_insert_event_persists_point_scope_and_widened_audit_fields(migrated_db):
    from sva.db import get_engine
    from sva.events_dao import derive_pass_count_for_point, insert_events, list_event_rows, list_event_rows_for_point

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

    insert_events(
        [
            Event(
            event_id="evt_phase2_001",
            game_id=game_id,
            point_id=f"{game_id}:pt_001",
            point_ordinal=1,
            video_ts_ms=1000,
            in_point_ts_ms=1000,
            type="completion",
            team="dark",
            throw_type="backhand",
            pass_direction="lateral",
            prompt_version_hash="abc123def456",
            rule_refs=["WFDF-12.1"],
            warnings=["best-effort"],
            model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
            ),
            Event(
                event_id="evt_phase2_001b",
                game_id=game_id,
                point_id=f"{game_id}:pt_001",
                point_ordinal=1,
                video_ts_ms=1200,
                in_point_ts_ms=1200,
                type="completion",
                team="dark",
                throw_type="forehand",
                pass_direction="up-field",
                prompt_version_hash="abc123def456",
                rule_refs=["WFDF-13.1"],
                model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
            ),
            Event(
            event_id="evt_phase2_002",
            game_id=game_id,
            point_id=f"{game_id}:pt_002",
            point_ordinal=2,
            video_ts_ms=22000,
            in_point_ts_ms=500,
            type="turnover",
            team="light",
            turnover_subtype="block",
            prompt_version_hash="def456abc123",
            rule_refs=["WFDF-13.2"],
            model=ModelMetadata(provider="dummy", model_id="dummy-llm", version="test"),
            ),
        ]
    )

    point_one_rows = list_event_rows_for_point(game_id, f"{game_id}:pt_001")
    assert len(point_one_rows) == 2
    assert point_one_rows[0].point_id == f"{game_id}:pt_001"
    assert point_one_rows[0].point_ordinal == 1
    assert int(point_one_rows[0].in_point_ts_ms) == 1000
    assert point_one_rows[1].event_id == "evt_phase2_001b"

    completion_rows = list_event_rows(game_id, point_id=f"{game_id}:pt_001", event_type="completion")
    assert len(completion_rows) == 2

    light_rows = list_event_rows(game_id, team="light")
    assert len(light_rows) == 1
    assert light_rows[0].event_id == "evt_phase2_002"

    assert derive_pass_count_for_point(game_id, f"{game_id}:pt_001") == 2

    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT point_id, point_ordinal, in_point_ts_ms, throw_type, pass_direction, "
                "prompt_version_hash, rule_refs, warnings "
                "FROM events WHERE game_id = :g AND point_id = :p ORDER BY video_ts_ms"
            ),
            {"g": game_id, "p": f"{game_id}:pt_001"},
        ).fetchall()
        turnover_row = conn.execute(
            text(
                "SELECT turnover_subtype, prompt_version_hash, rule_refs "
                "FROM events WHERE game_id = :g AND point_id = :p"
            ),
            {"g": game_id, "p": f"{game_id}:pt_002"},
        ).fetchone()

    assert len(rows) == 2
    assert rows[0].point_id == f"{game_id}:pt_001"
    assert rows[0].point_ordinal == 1
    assert int(rows[0].in_point_ts_ms) == 1000
    assert rows[0].throw_type == "backhand"
    assert rows[0].pass_direction == "lateral"
    assert rows[0].prompt_version_hash == "abc123def456"
    assert rows[0].rule_refs == ["WFDF-12.1"]
    assert rows[0].warnings == ["best-effort"]
    assert turnover_row is not None
    assert turnover_row.turnover_subtype == "block"
    assert turnover_row.prompt_version_hash == "def456abc123"
    assert turnover_row.rule_refs == ["WFDF-13.2"]

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
