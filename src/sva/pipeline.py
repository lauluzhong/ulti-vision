"""Narrow vertical slice end-to-end orchestrator.

Flows: ingest_clip -> per-window perceive -> interpret -> events.
This is Phase 1 scope only. Phase 6 replaces this with a Dramatiq durable workflow.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from sva.db import get_engine
from sva.events_dao import insert_event
from sva.ingest import IngestResult, ingest_clip
from sva.interpret import make_default_interpreter, run_point
from sva.memory import MemoryRetriever, RetrievalQuery
from sva.models import Event, Observation
from sva.observability import TraceContext
from sva.perceive import PerceiveWindow, make_default_perceiver, run_window

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    game_id: str
    video_id: str
    duration_s: float
    windows_processed: int
    observations: int
    events_inserted: int
    total_cost_usd: Decimal
    ingest: IngestResult


def _read_total_cost(game_id: str) -> Decimal:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT cost_usd FROM jobs WHERE game_id = :g"),
            {"g": game_id},
        ).scalar()
    return Decimal(row) if row is not None else Decimal("0")


def run_pipeline(
    source_path: Path | str,
    game_id: str | None = None,
) -> PipelineResult:
    """Run one clip through the Phase 1 narrow vertical slice."""
    ing = ingest_clip(source_path, game_id=game_id)
    logger.info("Ingested %s -> %s (game_id=%s)", ing.source_path, ing.transcoded_path, ing.game_id)

    perceiver = make_default_perceiver()
    interpreter = make_default_interpreter()
    retriever = MemoryRetriever()

    base_ctx = TraceContext(
        stage="pipeline",
        model="pipeline",
        video_id=ing.video_id,
        game_id=ing.game_id,
    )
    _ = base_ctx  # retained for future use; per-call contexts below supersede

    observations: list[Observation] = []
    for start_ms, end_ms in ing.windows:
        window = PerceiveWindow(
            window_id=f"win_{ing.video_id}_{start_ms}",
            video_id=ing.video_id,
            video_ts_start_ms=start_ms,
            video_ts_end_ms=end_ms,
            transcoded_path=ing.transcoded_path,
        )
        window_ctx = TraceContext(
            stage="perceive",
            model=getattr(perceiver, "model_id", "unknown"),
            video_id=ing.video_id,
            game_id=ing.game_id,
            window_id=window.window_id,
        )
        try:
            obs = run_window(window_ctx, window, perceiver=perceiver)
            observations.append(obs)
        except Exception as exc:
            logger.exception("perceive failed for window %s: %s", window.window_id, exc)

    # Phase 1 memory: zero-retrieval stub (D-08).
    retrieved = asyncio.run(
        retriever.retrieve(
            RetrievalQuery(event_candidate_type="unknown", context_text=""),
        )
    )

    events_inserted = 0
    if observations:
        interpret_ctx = TraceContext(
            stage="interpret",
            model=getattr(interpreter, "model_id", "unknown"),
            video_id=ing.video_id,
            game_id=ing.game_id,
            point_id=None,  # Phase 2 will fill this in
        )
        event: Event = run_point(interpret_ctx, observations, interpreter=interpreter, retrieved=retrieved)
        insert_event(event)
        events_inserted = 1

    total_cost = _read_total_cost(ing.game_id)

    # Mark job as complete.
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE jobs SET status = 'complete', updated_at = now() WHERE game_id = :g"),
            {"g": ing.game_id},
        )

    return PipelineResult(
        game_id=ing.game_id,
        video_id=ing.video_id,
        duration_s=ing.duration_s,
        windows_processed=len(ing.windows),
        observations=len(observations),
        events_inserted=events_inserted,
        total_cost_usd=total_cost,
        ingest=ing,
    )


__all__ = ["run_pipeline", "PipelineResult"]
