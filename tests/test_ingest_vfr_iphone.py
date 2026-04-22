"""INGEST-04 acceptance test: iPhone HEVC VFR clip ingests with event timestamps within +/-2s
of manually-verified ground truth.

REQUIRED FIXTURES (developer one-time setup):
  - tests/fixtures/iphone_hevc_vfr_90s.mov    -- real device-captured iPhone HEVC clip (~90s)
  - tests/fixtures/iphone_hevc_vfr_90s.groundtruth.json -- manually-verified event timestamps

The test FAILS LOUDLY (not skips) if either file is missing. Do NOT synthesize the fixture
with ffmpeg -- only a real device-captured file exercises the VFR timestamp drift path.

groundtruth.json format:
  {"pull_start_ms": 12000, "first_completion_ms": 18500, "goal_ms": 74200}

Keys must match event types emitted by the pipeline. Each value is a manually-confirmed
video_ts_ms in milliseconds for a clear visible event in the clip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

FIXTURES = Path("tests/fixtures")
IPHONE_FIXTURE = FIXTURES / "iphone_hevc_vfr_90s.mov"
GROUNDTRUTH_FILE = FIXTURES / "iphone_hevc_vfr_90s.groundtruth.json"
TOLERANCE_MS = 2000  # +/-2 seconds


def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _require_real_fixtures_or_fail() -> None:
    """Fail loudly (not skip) if fixture or groundtruth file is missing.

    Per plan INGEST-04 acceptance criteria: this test must NEVER silently skip
    when the fixture is missing. Skipping only happens when the fixture + groundtruth
    are present but the DB is unreachable -- the developer is on the right track but
    needs to start Postgres.
    """
    if not IPHONE_FIXTURE.exists():
        pytest.fail(
            f"INGEST-04 fixture missing: {IPHONE_FIXTURE}\n"
            "Drop a real device-captured iPhone HEVC clip (~90s) at this path.\n"
            "Do NOT synthesize it with ffmpeg -- only a real device clip exercises VFR drift."
        )
    if not GROUNDTRUTH_FILE.exists():
        pytest.fail(
            f"INGEST-04 groundtruth missing: {GROUNDTRUTH_FILE}\n"
            "Create a JSON file with manually-verified event timestamps, e.g.:\n"
            '  {"pull_start_ms": 12000, "first_completion_ms": 18500, "goal_ms": 74200}\n'
            "Each value is a video_ts_ms (milliseconds) for a clearly visible event in the clip."
        )


def test_iphone_hevc_vfr_ingest_event_timestamps_within_2s_of_groundtruth():
    """INGEST-04 gate -- event-level timestamps must be within +/-2000ms of manually-verified groundtruth.

    This test validates that the VFR->CFR transcode preserves temporal accuracy at the
    event level, not just total duration. Circular duration comparison (source vs transcoded)
    is insufficient -- it only proves transcode preserved length, not frame-level timing.
    """
    # Fail loudly first if fixture is missing -- never silent-skip on a missing fixture.
    _require_real_fixtures_or_fail()

    # Only *after* the fixture is proven present do we gate on DB reachability.
    if not _db_reachable():
        pytest.skip("Postgres unreachable; start `docker compose up -d db`")

    from sva.db import get_engine
    from sva.pipeline import run_pipeline

    groundtruth: dict[str, int] = json.loads(GROUNDTRUTH_FILE.read_text())
    assert groundtruth, "groundtruth.json must contain at least one event timestamp"

    game_id = "test_ingest_04_iphone_vfr_groundtruth"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})

    result = run_pipeline(IPHONE_FIXTURE, game_id=game_id)

    # Fetch all persisted events for this run.
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT video_ts_ms FROM events WHERE game_id = :g ORDER BY video_ts_ms"),
            {"g": game_id},
        ).fetchall()

    event_timestamps_ms = [int(row.video_ts_ms) for row in rows]
    assert event_timestamps_ms, (
        "Pipeline produced zero events for the iPhone fixture -- nothing to compare against groundtruth"
    )

    # For each groundtruth event, assert at least one pipeline event falls within +/-TOLERANCE_MS.
    misses: list[str] = []
    for gt_key, gt_ms in groundtruth.items():
        closest_delta = min(abs(ts - gt_ms) for ts in event_timestamps_ms)
        if closest_delta > TOLERANCE_MS:
            misses.append(
                f"  groundtruth['{gt_key}']={gt_ms}ms: closest event was {closest_delta}ms away "
                f"(tolerance={TOLERANCE_MS}ms)"
            )

    assert not misses, (
        f"INGEST-04 FAILED: {len(misses)} groundtruth event(s) not matched within +/-{TOLERANCE_MS}ms:\n"
        + "\n".join(misses)
    )

    # CFR transcode must be confirmed.
    assert result.ingest.transcoded_metadata.is_variable_fps is False, (
        "Transcoded output is still VFR -- CFR transcode failed"
    )

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM events WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
