"""Per-call cost estimator using published 2026-04 rates (see STACK.md).

v0: Gemini Flash powers both VLM (perceive) and LLM (interpret) so this
module only needs Gemini rates. To add another provider (DeepSeek, GPT-4o-mini,
Kimi K2, etc.), add a `_<PROVIDER>_RATES` table and an `estimate_<provider>_cost`
function — same shape as below.
"""

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


def estimate_gemini_cost(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    model: str = "gemini-2.5-flash",
) -> Decimal:
    """Estimated USD cost for one Gemini call (text or video, both stages)."""
    rates = _GEMINI_RATES.get(model, _GEMINI_RATES["gemini-2.5-flash"])
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


__all__ = ["estimate_gemini_cost", "record_job_cost"]
