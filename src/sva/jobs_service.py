"""Durable job submission and resume-safe orchestration helpers."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from sva.events_dao import insert_events, list_event_rows_for_point
from sva.ingest import IngestResult, ingest_local_file, ingest_remote_url, load_ingest_result_for_job
from sva.ingest.sampler import make_window_id
from sva.ingest.sources import LocalFileSource, RemoteUrlSource, validate_local_source, validate_remote_source
from sva.interpret import make_default_interpreter, run_point
from sva.jobs_dao import JobRecord, get_job, upsert_job
from sva.memory import MemoryRetriever, RetrievalQuery
from sva.models import Observation
from sva.observability import TraceContext
from sva.perceive import PerceiveWindow, insert_observations, make_default_perceiver, run_window
from sva.pipeline import (
    PipelineResult,
    _apply_point_scope,
    _build_point_boundary_candidates,
    _resolve_window_point,
)
from sva.points import detect_points
from sva.points.dao import insert_points, list_points

logger = logging.getLogger(__name__)


def _generate_game_id() -> str:
    return f"game_{uuid.uuid4().hex[:8]}"


def _base_progress(*, target_fps: int, caller_id: str | None = None) -> dict[str, Any]:
    progress: dict[str, Any] = {
        "target_fps": target_fps,
        "points_total": 0,
        "points_completed": 0,
        "windows_total": 0,
        "windows_completed": 0,
        "events_inserted": 0,
    }
    if caller_id is not None:
        progress["caller_id"] = caller_id
    return progress


def submit_local_job(
    path: Path | str,
    *,
    game_id: str | None = None,
    target_fps: int = 1,
) -> JobRecord:
    validated = validate_local_source(LocalFileSource(path=Path(path)))
    return upsert_job(
        game_id=game_id or _generate_game_id(),
        status="queued",
        stage="queued",
        progress=_base_progress(target_fps=target_fps),
        error_message=None,
        source_path=str(Path(validated.path).resolve()),
        source_kind="local_file",
    )


def submit_remote_job(
    url: str,
    *,
    caller_id: str,
    ack_rights: bool,
    game_id: str | None = None,
    target_fps: int = 1,
) -> JobRecord:
    validated = validate_remote_source(
        RemoteUrlSource(url=url, caller_id=caller_id, ack_rights=ack_rights)
    )
    progress = _base_progress(target_fps=target_fps, caller_id=caller_id)
    progress["ack_rights"] = True
    return upsert_job(
        game_id=game_id or _generate_game_id(),
        status="queued",
        stage="queued",
        progress=progress,
        error_message=None,
        source_kind="public_url",
        source_url=validated.url,
    )


def process_job(game_id: str) -> PipelineResult:
    job = _require_job(game_id)
    target_fps = int((job.progress or {}).get("target_fps", 1) or 1)
    progress = _base_progress(
        target_fps=target_fps,
        caller_id=(job.progress or {}).get("caller_id"),
    )
    progress.update(job.progress or {})
    current_stage = "queued"
    try:
        current_stage = "ingest"
        upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress, error_message=None)
        ing = _ensure_ingested(job, target_fps=target_fps)
        progress["windows_total"] = len(ing.windows)
        progress["windows_completed"] = 0

        current_stage = "point_detect"
        upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress)
        points = list_points(ing.game_id)
        if not points:
            point_candidates = _build_point_boundary_candidates(ing)
            points = detect_points(ing.game_id, point_candidates)
            if points:
                insert_points(points)
            points = list_points(ing.game_id)
        progress["points_total"] = len(points)

        perceiver = make_default_perceiver()
        interpreter = make_default_interpreter()
        retriever = MemoryRetriever()
        windows_by_point = _group_windows_by_point(ing, points, target_fps=target_fps)

        events_inserted = 0
        observations_count = 0
        for point in points:
            point_windows = windows_by_point.get(point.point_id, [])
            if list_event_rows_for_point(ing.game_id, point.point_id):
                progress["points_completed"] += 1
                progress["windows_completed"] += len(point_windows)
                upsert_job(game_id=game_id, status="running", stage="persist", progress=progress)
                continue

            current_stage = "perceive"
            point_observations: list[Observation] = []
            for window in point_windows:
                window_ctx = TraceContext(
                    stage="perceive",
                    model=getattr(perceiver, "model_id", "unknown"),
                    video_id=ing.video_id,
                    game_id=ing.game_id,
                    window_id=window.window_id,
                    point_id=point.point_id,
                    point_ordinal=point.point_ordinal,
                )
                observation = run_window(
                    window_ctx,
                    window,
                    perceiver=perceiver,
                    on_cache_miss=lambda fresh_observation, prompt_hash, owning_point=point: insert_observations(
                        game_id=ing.game_id,
                        point_id=owning_point.point_id,
                        point_ordinal=owning_point.point_ordinal,
                        prompt_version_hash=prompt_hash,
                        observations=[fresh_observation],
                    ),
                )
                point_observations.append(observation)
                observations_count += 1
                progress["windows_completed"] += 1
                upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress)

            if not point_observations:
                continue

            current_stage = "interpret"
            upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress)
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
            events = run_point(
                interpret_ctx,
                point_observations,
                interpreter=interpreter,
                retrieved=retrieved,
            )
            scoped_events = [
                _apply_point_scope(
                    event,
                    point,
                    fallback_ts_ms=point_observations[0].observation_ts_ms,
                )
                for event in events
            ]

            current_stage = "persist"
            if scoped_events:
                insert_events(scoped_events)
                events_inserted += len(scoped_events)
                progress["events_inserted"] += len(scoped_events)
            progress["points_completed"] += 1
            upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress)

        current_stage = "complete"
        final_job = upsert_job(
            game_id=game_id,
            status="complete",
            stage=current_stage,
            progress=progress,
            error_message=None,
        )
        return PipelineResult(
            game_id=ing.game_id,
            video_id=ing.video_id,
            duration_s=ing.duration_s,
            windows_processed=len(ing.windows),
            observations=observations_count,
            events_inserted=events_inserted,
            total_cost_usd=final_job.cost_usd if isinstance(final_job.cost_usd, Decimal) else Decimal("0"),
            ingest=ing,
        )
    except Exception as exc:
        logger.exception("job processing failed for %s", game_id)
        upsert_job(
            game_id=game_id,
            status="failed",
            stage=current_stage,
            progress=progress,
            error_message=str(exc),
        )
        raise


def _require_job(game_id: str) -> JobRecord:
    job = get_job(game_id)
    if job is None:
        raise ValueError(f"Unknown job/game_id: {game_id}")
    return job


def _ensure_ingested(job: JobRecord, *, target_fps: int) -> IngestResult:
    if job.video_id:
        return load_ingest_result_for_job(job.game_id, target_fps=target_fps)
    if job.source_kind == "public_url":
        if not job.source_url:
            raise ValueError(f"Remote job {job.game_id} is missing source_url")
        caller_id = str((job.progress or {}).get("caller_id", "api"))
        return ingest_remote_url(
            job.source_url,
            caller_id=caller_id,
            ack_rights=True,
            game_id=job.game_id,
            target_fps=target_fps,
        )
    if not job.source_path:
        raise ValueError(f"Local job {job.game_id} is missing source_path")
    return ingest_local_file(job.source_path, game_id=job.game_id, target_fps=target_fps)


def _group_windows_by_point(
    ing: IngestResult,
    points,
    *,
    target_fps: int,
) -> dict[str, list[PerceiveWindow]]:
    grouped: dict[str, list[PerceiveWindow]] = defaultdict(list)
    for start_ms, end_ms in ing.windows:
        owning_point = _resolve_window_point(points, start_ms, end_ms)
        if owning_point is None:
            continue
        grouped[owning_point.point_id].append(
            PerceiveWindow(
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
        )
    return grouped


__all__ = ["process_job", "submit_local_job", "submit_remote_job"]
