"""Phase 1 tests: GeminiPerceiver stub emits a valid Observation + Langfuse trace path."""

from __future__ import annotations

import pytest
from sqlalchemy import text


def _db_reachable() -> bool:
    try:
        from sva.db import get_engine

        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable")
def test_gemini_perceiver_emits_valid_observation():
    from sva.db import get_engine
    from sva.observability import TraceContext
    from sva.perceive import GeminiPerceiver, PerceiveWindow

    game_id = "test_perceive_game_1"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
        conn.execute(
            text("INSERT INTO jobs (game_id, video_id, status) VALUES (:g, :v, 'streaming')"),
            {"g": game_id, "v": "vid_test"},
        )

    window = PerceiveWindow(
        window_id="win_1",
        video_id="vid_test",
        video_ts_start_ms=0,
        video_ts_end_ms=2000,
        transcoded_path="/tmp/fake.mp4",
    )
    ctx = TraceContext(stage="perceive", model="gemini-2.5-flash", video_id="vid_test", game_id=game_id)

    obs = GeminiPerceiver().perceive(ctx, window)
    assert obs.schema_version == "1.0"
    assert obs.model.provider == "gemini"
    assert obs.model.model_id == "gemini-2.5-flash"
    assert obs.window_id == "win_1"
    assert 0 <= obs.confidence_overall <= 1

    # OBS-01: cost should have been recorded on the jobs row
    with get_engine().connect() as conn:
        cost = conn.execute(
            text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()
    assert cost is not None
    assert float(cost) > 0

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})
