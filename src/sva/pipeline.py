"""Narrow vertical slice end-to-end orchestrator.

Flows: ingest_clip -> per-window perceive -> interpret -> events.
This is Phase 1 scope only. Phase 6 replaces this with a Dramatiq durable workflow.
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
from sva.events_dao import insert_event
from sva.ingest import IngestResult, ingest_clip
from sva.ingest.sampler import make_window_id
from sva.interpret import make_default_interpreter, run_point
from sva.memory import MemoryRetriever, RetrievalQuery
from sva.models import Event, Observation
from sva.observability import TraceContext
from sva.perceive import PerceiveWindow, insert_observations, make_default_perceiver, run_window
from sva.points import BoundarySignal, PointBoundaryCandidate, PointRecord, detect_points
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


def _build_point_boundary_candidates(ing: IngestResult) -> list[PointBoundaryCandidate]:
    if not ing.windows:
        return []

    start_ms = ing.windows[0][0]
    end_ms = ing.windows[-1][1]

    # Bootstrap a single deterministic candidate until the full OCR/pull candidate
    # extractor lands; Phase 02-03's contract is that downstream work uses persisted
    # point rows as the authoritative grouping primitive.
    return [
        PointBoundaryCandidate(
            start_video_ts_ms=start_ms,
            end_video_ts_ms=end_ms,
            pull=BoundarySignal(
                source="pull",
                video_ts_ms=start_ms,
                confidence=1.0,
                details={"mode": "phase2_bootstrap_whole_game_point"},
            ),
        )
    ]


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


def run_pipeline(
    source_path: Path | str,
    game_id: str | None = None,
    *,
    target_fps: int = 1,
) -> PipelineResult:
    """Run one clip through the Phase 1 narrow vertical slice."""
    ing = ingest_clip(source_path, game_id=game_id, target_fps=target_fps)
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

    point_candidates = _build_point_boundary_candidates(ing)
    points = detect_points(ing.game_id, point_candidates)
    if points:
        insert_points(points)
    persisted_points = list_points(ing.game_id)

    observations: list[Observation] = []
    observations_by_point: dict[str, list[Observation]] = defaultdict(list)
    points_by_id = {point.point_id: point for point in persisted_points}
    for start_ms, end_ms in ing.windows:
        owning_point = _resolve_window_point(persisted_points, start_ms, end_ms)
        if owning_point is None:
            continue
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
            point_id=owning_point.point_id,
            point_ordinal=owning_point.point_ordinal,
        )
        try:
            obs = run_window(
                window_ctx,
                window,
                perceiver=perceiver,
                on_cache_miss=lambda observation, prompt_hash, point=owning_point: insert_observations(
                    game_id=ing.game_id,
                    point_id=point.point_id,
                    point_ordinal=point.point_ordinal,
                    prompt_version_hash=prompt_hash,
                    observations=[observation],
                ),
            )
            observations.append(obs)
            observations_by_point[owning_point.point_id].append(obs)
        except Exception as exc:
            logger.exception("perceive failed for window %s: %s", window.window_id, exc)

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
        event = run_point(interpret_ctx, point_observations, interpreter=interpreter, retrieved=retrieved)
        scoped_event = _apply_point_scope(
            event,
            point,
            fallback_ts_ms=point_observations[0].observation_ts_ms,
        )
        insert_event(scoped_event)
        events_inserted += 1

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
