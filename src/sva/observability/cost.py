"""Per-call cost estimator using published 2026-04 rates (see STACK.md)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from sva.db import session_scope

# Rates verified 2026-04-20 against official pricing pages.
_GEMINI_RATES = {
    "gemini-2.5-flash": {
        "input": Decimal("0.00000030"),         # $0.30 / 1M
        "output": Decimal("0.00000250"),        # $2.50 / 1M
        "cache_read": Decimal("0.00000003"),    # $0.03 / 1M
    },
    "gemini-2.5-pro": {
        "input": Decimal("0.00000125"),         # $1.25 / 1M (<=200k ctx)
        "output": Decimal("0.00001000"),        # $10.00 / 1M
        "cache_read": Decimal("0.00000012"),    # $0.125 / 1M
    },
}

_CLAUDE_RATES = {
    "claude-sonnet-4-5": {
        "input": Decimal("0.00000300"),         # $3 / 1M
        "output": Decimal("0.00001500"),        # $15 / 1M
        "cache_read": Decimal("0.00000030"),    # 0.1x input
    },
    "claude-opus-4-7": {
        "input": Decimal("0.00000500"),
        "output": Decimal("0.00002500"),
        "cache_read": Decimal("0.00000050"),
    },
}


def estimate_gemini_cost(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    model: str = "gemini-2.5-flash",
) -> Decimal:
    """Estimated USD cost for one Gemini call."""
    rates = _GEMINI_RATES.get(model, _GEMINI_RATES["gemini-2.5-flash"])
    fresh_input = max(input_tokens - cached_input_tokens, 0)
    return (
        Decimal(fresh_input) * rates["input"]
        + Decimal(cached_input_tokens) * rates["cache_read"]
        + Decimal(output_tokens) * rates["output"]
    )


def estimate_claude_cost(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    model: str = "claude-sonnet-4-5",
) -> Decimal:
    """Estimated USD cost for one Claude call."""
    rates = _CLAUDE_RATES.get(model, _CLAUDE_RATES["claude-sonnet-4-5"])
    fresh_input = max(input_tokens - cached_input_tokens, 0)
    return (
        Decimal(fresh_input) * rates["input"]
        + Decimal(cached_input_tokens) * rates["cache_read"]
        + Decimal(output_tokens) * rates["output"]
    )


def record_job_cost(game_id: str, delta_usd: Decimal) -> None:
    """Atomically add `delta_usd` to the jobs row keyed by game_id.

    If the row does not exist, inserts a stub row with status='streaming' so early trace
    recording doesn't silently drop cost. In normal operation the row is created by
    `sva.ingest.ingest_clip` before any VLM/LLM calls happen.
    """
    with session_scope() as session:
        result = session.execute(
            text(
                "UPDATE jobs SET cost_usd = cost_usd + :delta, updated_at = now() "
                "WHERE game_id = :gid"
            ),
            {"delta": delta_usd, "gid": game_id},
        )
        if result.rowcount == 0:
            session.execute(
                text(
                    "INSERT INTO jobs (game_id, video_id, status, cost_usd) "
                    "VALUES (:gid, :vid, 'streaming', :delta)"
                ),
                {"gid": game_id, "vid": f"vid_missing_{game_id}", "delta": delta_usd},
            )


__all__ = ["estimate_gemini_cost", "estimate_claude_cost", "record_job_cost"]
