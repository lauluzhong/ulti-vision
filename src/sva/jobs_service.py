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
from sva.models import MemoryRecord, Observation
from sva.observability import TraceContext
from sva.perceive import PerceiveWindow, insert_observations, make_default_perceiver, run_window
from sva.pipeline import (
    PipelineResult,
    _apply_point_scope,
    _resolve_window_point,
    _retrieve_perceive_memory,
)
from sva.points import detect_points_from_observations
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
    """Durable async job runner — mirrors sva.pipeline.run_pipeline but
    persists progress/stage updates to the jobs table on every transition.

    v0 flow: ingest -> perceive every window -> detect points from observations
    -> persist observations + points -> interpret per point -> persist events.
    """
    job = _require_job(game_id)
    target_fps = int((job.progress or {}).get("target_fps", 1) or 1)
    progress = _base_progress(
        target_fps=target_fps,
        caller_id=(job.progress or {}).get("caller_id"),
    )
    progress.update(job.progress or {})
    current_stage = "queued"
    try:
        # ----- Ingest -----
        current_stage = "ingest"
        upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress, error_message=None)
        ing = _ensure_ingested(job, target_fps=target_fps)
        progress["windows_total"] = len(ing.windows)
        progress["windows_completed"] = 0

        # ----- Perceive every window -----
        current_stage = "perceive"
        upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress)

        perceiver = make_default_perceiver()
        interpreter = make_default_interpreter()
        retriever = MemoryRetriever()
        perceive_memory = _retrieve_perceive_memory(retriever, ing.game_id)

        observations: list[Observation] = []
        fresh_persists: list[tuple[Observation, str]] = []  # (obs, prompt_hash) for cache misses

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
            # Perception errors propagate to the outer try/except so the job goes
            # to "failed" status. The on_cache_miss callback fires before the
            # exception, so observations from any windows that completed before
            # the crash are durably cached and reused on the next run.
            observation = run_window(
                window_ctx,
                window,
                perceiver=perceiver,
                retrieved=perceive_memory,
                on_cache_miss=_record_cache_miss,
            )
            observations.append(observation)
            progress["windows_completed"] += 1
            upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress)

        # ----- Detect points from observations -----
        current_stage = "point_detect"
        upsert_job(game_id=game_id, status="running", stage=current_stage, progress=progress)
        points = detect_points_from_observations(ing.game_id, observations)
        if points:
            insert_points(points)
        persisted_points = list_points(ing.game_id)
        points_by_id = {point.point_id: point for point in persisted_points}
        progress["points_total"] = len(persisted_points)

        # Persist cache-miss observations now that we know their owning points.
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

        # ----- Interpret per point -----
        observations_by_point: dict[str, list[Observation]] = defaultdict(list)
        for obs in observations:
            owning = _resolve_window_point(
                persisted_points, obs.video_ts_start_ms, obs.video_ts_end_ms
            )
            if owning is not None:
                observations_by_point[owning.point_id].append(obs)

        events_inserted = 0
        for point in persisted_points:
            point_observations = observations_by_point.get(point.point_id, [])
            if not point_observations:
                progress["points_completed"] += 1
                continue
            if list_event_rows_for_point(ing.game_id, point.point_id):
                # Resume-safe: events already exist for this point, skip re-interpret.
                progress["points_completed"] += 1
                upsert_job(game_id=game_id, status="running", stage="persist", progress=progress)
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

        # ----- Complete -----
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
            observations=len(observations),
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


__all__ = ["process_job", "submit_local_job", "submit_remote_job"]
