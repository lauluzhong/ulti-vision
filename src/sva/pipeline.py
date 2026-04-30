"""End-to-end pipeline orchestrator.

v0 flow: ingest -> perceive every window -> detect points from observations
-> interpret per point -> persist events.

Critical change from prior bootstrap: point detection now runs AFTER perception,
using VLM-observed game phase signals (pre_pull / live_play / score_celebration /
between_points) to find real point boundaries. The old whole-game-as-one-point
bootstrap is gone.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from sva.db import get_engine
from sva.events_dao import insert_events
from sva.ingest import IngestResult, ingest_clip
from sva.ingest.sampler import make_window_id
from sva.interpret import make_default_interpreter, run_point
from sva.memory import MemoryRetriever, RetrievalQuery
from sva.models import Event, MemoryRecord, Observation
from sva.observability import TraceContext
from sva.perceive import PerceiveWindow, insert_observations, make_default_perceiver, run_window
from sva.points import PointRecord, detect_points_from_observations
from sva.points.dao import insert_points, list_points

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


def _mark_job_complete(game_id: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE jobs SET status = 'complete', updated_at = now() WHERE game_id = :g"),
            {"g": game_id},
        )


def _resolve_window_point(points: list[PointRecord], start_ms: int, end_ms: int) -> PointRecord | None:
    midpoint_ms = (start_ms + end_ms) // 2
    for point in points:
        if point.start_video_ts_ms <= midpoint_ms <= point.end_video_ts_ms:
            return point
    return None


def _apply_point_scope(event: Event, point: PointRecord, fallback_ts_ms: int) -> Event:
    absolute_ts_ms = event.video_ts_ms if event.video_ts_ms is not None else fallback_ts_ms
    if absolute_ts_ms < point.start_video_ts_ms:
        absolute_ts_ms = fallback_ts_ms
    in_point_ts_ms = max(absolute_ts_ms - point.start_video_ts_ms, 0)
    return event.model_copy(
        update={
            "point_id": point.point_id,
            "point_ordinal": point.point_ordinal,
            "video_ts_ms": absolute_ts_ms,
            "in_point_ts_ms": in_point_ts_ms,
        }
    )


def _retrieve_perceive_memory(
    retriever: MemoryRetriever,
    game_id: str,
) -> list[MemoryRecord]:
    """Pull general perception-relevant memory before VLM calls.

    For v0, retrieve memories tagged 'perceive' or coach-scoped general guidance
    (no event-type filter — we don't yet know what events the window contains).
    Empty list when memory is empty (cold start).
    """
    try:
        return asyncio.run(
            retriever.retrieve(
                RetrievalQuery(
                    event_candidate_type="unknown",
                    context_text="perceive perception vlm",
                )
            )
        )
    except Exception as exc:  # pragma: no cover - retrieval is non-fatal
        logger.warning("perceive memory retrieval failed (non-fatal): %s", exc)
        return []


def run_pipeline(
    source_path: Path | str,
    game_id: str | None = None,
    *,
    target_fps: int = 1,
) -> PipelineResult:
    """Run one clip end-to-end: ingest -> perceive -> detect points -> interpret."""
    ing = ingest_clip(source_path, game_id=game_id, target_fps=target_fps)
    logger.info("Ingested %s -> %s (game_id=%s)", ing.source_path, ing.transcoded_path, ing.game_id)

    perceiver = make_default_perceiver()
    interpreter = make_default_interpreter()
    retriever = MemoryRetriever()

    # Stage 1: perceive every window. No point context yet — point detection
    # consumes the VLM's structured output to find real boundaries.
    perceive_memory = _retrieve_perceive_memory(retriever, ing.game_id)
    observations: list[Observation] = []
    fresh_persists: list[tuple[Observation, str]] = []  # (observation, prompt_hash) for cache misses

    def _record_cache_miss(observation: Observation, prompt_hash: str) -> None:
        fresh_persists.append((observation, prompt_hash))

    for start_ms, end_ms in ing.windows:
        window = PerceiveWindow(
            window_id=make_window_id(
                video_id=ing.video_id,
                start_ms=start_ms,
                end_ms=end_ms,
                fps=target_fps,
            ),
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
            obs = run_window(
                window_ctx,
                window,
                perceiver=perceiver,
                retrieved=perceive_memory,
                on_cache_miss=_record_cache_miss,
            )
            observations.append(obs)
        except Exception as exc:
            logger.exception("perceive failed for window %s: %s", window.window_id, exc)

    # Stage 2: detect points from VLM observations.
    points = detect_points_from_observations(ing.game_id, observations)
    if points:
        insert_points(points)
    persisted_points = list_points(ing.game_id)
    points_by_id = {point.point_id: point for point in persisted_points}

    # Stage 3: persist cache-miss observations now that we know their owning points.
    for observation, prompt_hash in fresh_persists:
        owning = _resolve_window_point(
            persisted_points, observation.video_ts_start_ms, observation.video_ts_end_ms
        )
        if owning is None:
            continue
        try:
            insert_observations(
                game_id=ing.game_id,
                point_id=owning.point_id,
                point_ordinal=owning.point_ordinal,
                prompt_version_hash=prompt_hash,
                observations=[observation],
            )
        except Exception as exc:
            logger.warning("observation persist failed for %s: %s", observation.window_id, exc)

    # Stage 4: group observations by owning point and interpret each point.
    observations_by_point: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        owning = _resolve_window_point(
            persisted_points, obs.video_ts_start_ms, obs.video_ts_end_ms
        )
        if owning is not None:
            observations_by_point[owning.point_id].append(obs)

    events_inserted = 0
    for point_id, point_observations in observations_by_point.items():
        if not point_observations:
            continue
        point = points_by_id[point_id]
        retrieved = asyncio.run(
            retriever.retrieve(
                RetrievalQuery(event_candidate_type="unknown", context_text=""),
            )
        )
        interpret_ctx = TraceContext(
            stage="interpret",
            model=getattr(interpreter, "model_id", "unknown"),
            video_id=ing.video_id,
            game_id=ing.game_id,
            point_id=point.point_id,
            point_ordinal=point.point_ordinal,
        )
        events = run_point(interpret_ctx, point_observations, interpreter=interpreter, retrieved=retrieved)
        scoped_events = [
            _apply_point_scope(
                event,
                point,
                fallback_ts_ms=point_observations[0].observation_ts_ms,
            )
            for event in events
        ]
        if not scoped_events:
            continue
        insert_events(scoped_events)
        events_inserted += len(scoped_events)

    total_cost = _read_total_cost(ing.game_id)
    _mark_job_complete(ing.game_id)

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
