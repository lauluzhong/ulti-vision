"""End-to-end CLI test: ingest -> perceive stub -> interpret stub -> Event row."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

FIXTURES = Path("tests/fixtures")
VFR_SYNTHETIC = FIXTURES / "vfr_synthetic.mp4"


def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _ensure_vfr_fixture():
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not found")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    if not VFR_SYNTHETIC.exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "testsrc=duration=10:size=320x240:rate=30",
                "-vf",
                "settb=AVTB,setpts=if(lt(N\\,30)\\,N/3\\,if(lt(N\\,60)\\,N/10\\,N/30))/TB",
                "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(VFR_SYNTHETIC),
            ],
            check=True,
            capture_output=True,
        )


@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
def test_run_pipeline_produces_event_row():
    from sva.db import get_engine
    from sva.pipeline import run_pipeline

    game_id = "test_e2e_pipeline_game_1"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})

    result = run_pipeline(VFR_SYNTHETIC, game_id=game_id)

    # Phase 1 success criterion #1 — assertions:
    assert result.windows_processed > 0
    assert result.observations > 0
    assert result.events_inserted == 1
    assert result.total_cost_usd > 0

    # Verify DB rows
    with get_engine().connect() as conn:
        job_row = conn.execute(
            text("SELECT status, cost_usd, duration_s FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).fetchone()
        event_count = conn.execute(
            text("SELECT count(*) FROM events WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()

    assert job_row is not None
    assert job_row.status == "complete"
    assert float(job_row.cost_usd) > 0
    assert event_count == 1

    # Cleanup
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
