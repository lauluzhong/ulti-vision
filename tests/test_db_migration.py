"""DB migration smoke test — requires Docker compose 'db' service running.

Skips automatically if DATABASE_URL does not point at a reachable Postgres.
"""

from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import text


def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def migrated_db():
    if not _db_reachable():
        pytest.skip("Postgres not reachable; start with `docker compose up -d db`")
    # Bring DB to head.
    env = os.environ.copy()
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    yield
    # Leave schema in place — downstream plans expect head state.


def test_jobs_and_events_tables_exist(migrated_db):
    from sva.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        ).scalars().all()
    assert "jobs" in rows
    assert "events" in rows


def test_phase2_rights_ack_table_exists_when_migrated(migrated_db):
    from sva.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        ).scalars().all()
    assert "rights_acks" in rows


def test_phase3_observations_table_exists_when_migrated(migrated_db):
    from sva.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        ).scalars().all()
    assert "observations" in rows


def test_phase4_event_audit_columns_exist_when_migrated(migrated_db):
    from sva.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='events' ORDER BY column_name"
            )
        ).scalars().all()
    for column in [
        "turnover_subtype",
        "throw_type",
        "pass_direction",
        "prompt_version_hash",
        "rule_refs",
        "warnings",
    ]:
        assert column in rows


def test_phase5_memory_and_corrections_tables_exist_when_migrated(migrated_db):
    from sva.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        ).scalars().all()
    assert "memory_records" in rows
    assert "corrections" in rows


def test_cost_aggregation_query_works(migrated_db):
    from sva.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        total = conn.execute(
            text("SELECT COALESCE(SUM(cost_usd), 0) FROM jobs WHERE game_id = :g"),
            {"g": "nonexistent_game"},
        ).scalar()
    assert total == 0


def test_pgvector_extension_present(migrated_db):
    from sva.db import get_engine

    eng = get_engine()
    with eng.connect() as conn:
        ext = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        ).scalar()
    assert ext == "vector"
