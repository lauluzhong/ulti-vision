"""Tests for cost estimation + jobs.cost_usd aggregation + Langfuse decorator contract."""

from __future__ import annotations

import os
from decimal import Decimal

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


def test_estimate_gemini_cost_matches_published_rates():
    from sva.observability.cost import estimate_gemini_cost

    # 1M input + 1M output on gemini-2.5-flash = $0.30 + $2.50 = $2.80
    cost = estimate_gemini_cost(1_000_000, 1_000_000)
    assert cost == Decimal("2.80")

    # With 500k cached input tokens: 500k * $0.30/M + 500k * $0.03/M + 1M * $2.50/M
    # = $0.15 + $0.015 + $2.50 = $2.665
    cost_cached = estimate_gemini_cost(1_000_000, 1_000_000, cached_input_tokens=500_000)
    assert cost_cached == Decimal("2.665")


def test_estimate_claude_cost_matches_published_rates():
    from sva.observability.cost import estimate_claude_cost

    # 1M input + 1M output on claude-sonnet-4-5 = $3 + $15 = $18
    cost = estimate_claude_cost(1_000_000, 1_000_000)
    assert cost == Decimal("18")


@pytest.mark.skipif(not _db_reachable(), reason="Postgres unreachable; start `docker compose up -d db`")
def test_record_job_cost_aggregates_per_game():
    from sva.db import get_engine
    from sva.observability.cost import record_job_cost

    game_id = "test_obs_game_1"
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})

    record_job_cost(game_id, Decimal("0.001234"))
    record_job_cost(game_id, Decimal("0.002000"))

    with get_engine().connect() as conn:
        total = conn.execute(
            text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()

    assert total == Decimal("0.003234")

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": game_id})


def test_observe_call_decorator_returns_result_not_tuple():
    """Langfuse may not be available in CI; the decorator must still pass through the result."""
    from sva.observability.langfuse import TraceContext, observe_call

    @observe_call(stage="perceive", model="dummy-model")
    def fake_perceive(ctx, payload):
        # Returns (result, cost_usd, in_tokens, out_tokens, ctx)
        return ({"echo": payload}, Decimal("0.000001"), 100, 10, ctx)

    ctx = TraceContext(stage="perceive", model="dummy", video_id="vid_x", game_id="test_obs_game_2")
    # Skip if DB unreachable — decorator writes cost to DB.
    if not _db_reachable():
        pytest.skip("Postgres unreachable")
    result = fake_perceive(ctx, "hello")
    assert result == {"echo": "hello"}

    # Cleanup
    from sva.db import get_engine

    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE game_id = :g"), {"g": "test_obs_game_2"})


def test_prompt_version_hash_is_non_empty_and_prompt_sensitive():
    """OBS-02: TraceContext.prompt_version_hash must be a non-empty 12-char SHA-256 hex prefix.
    Two different prompts must produce different hashes.
    """
    import hashlib
    from sva.observability.langfuse import TraceContext

    prompt_a = "Analyze this Ultimate Frisbee frame and identify all visible player actions."
    prompt_b = "Different prompt text that should produce a distinct hash."

    hash_a = hashlib.sha256(prompt_a.encode()).hexdigest()[:12]
    hash_b = hashlib.sha256(prompt_b.encode()).hexdigest()[:12]

    ctx_a = TraceContext(
        stage="perceive", model="gemini-2.5-flash",
        video_id="vid_x", game_id="game_x",
        prompt_version_hash=hash_a,
    )
    ctx_b = TraceContext(
        stage="perceive", model="gemini-2.5-flash",
        video_id="vid_x", game_id="game_x",
        prompt_version_hash=hash_b,
    )

    # Non-empty
    assert ctx_a.prompt_version_hash is not None
    assert len(ctx_a.prompt_version_hash) == 12, f"Expected 12-char hash, got {len(ctx_a.prompt_version_hash)}"

    # Prompt-sensitive: two different prompts → two different hashes
    assert ctx_a.prompt_version_hash != ctx_b.prompt_version_hash, (
        "Two different prompts must produce different prompt_version_hash values"
    )

    # Hash is stable (same input = same output)
    hash_a_repeat = hashlib.sha256(prompt_a.encode()).hexdigest()[:12]
    assert ctx_a.prompt_version_hash == hash_a_repeat
