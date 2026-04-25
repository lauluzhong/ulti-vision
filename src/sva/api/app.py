"""Thin async submission and polling FastAPI surface for Phase 6."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from sva.api.contracts import (
    CorrectionCreateRequest,
    CorrectionResponse,
    EventResponse,
    GameEventsResponse,
    GamePointsResponse,
    JobStatusResponse,
    JobSubmissionResponse,
    PointBoundaryResponse,
    PointBoundaryUpdateRequest,
    PointBoundaryUpdateResponse,
)
from sva.events_dao import list_event_rows
from sva.exports import render_events_csv
from sva.jobs_dao import get_job
from sva.jobs_service import submit_local_job, submit_remote_job
from sva.memory.service import CorrectionSubmission, submit_correction
from sva.points.dao import list_points
from sva.points.service import PointBoundaryPatch, replace_point_boundaries
from sva.queue import enqueue_job
from sva.ingest.ingest import TRANSCODED_DIR

try:
    from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
    from fastapi.responses import FileResponse
except ModuleNotFoundError:  # pragma: no cover - depends on installed extras
    FastAPI = None  # type: ignore[assignment]
    File = Form = Response = UploadFile = HTTPException = FileResponse = None  # type: ignore[assignment]


UPLOAD_DIR = Path("data/uploads")

def _save_upload(upload: Any) -> Path:
    suffix = Path(upload.filename or "upload.bin").suffix or ".bin"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dst = UPLOAD_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
    with dst.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return dst


def _serialize_event_row(row: Any) -> EventResponse:
    confidence = None if row.confidence is None else float(row.confidence)
    return EventResponse(
        event_id=row.event_id,
        game_id=row.game_id,
        point_id=row.point_id,
        point_ordinal=int(row.point_ordinal),
        video_ts_ms=int(row.video_ts_ms),
        in_point_ts_ms=int(row.in_point_ts_ms),
        type=row.type,
        team=row.team,
        turnover_subtype=row.turnover_subtype,
        throw_type=row.throw_type,
        pass_direction=row.pass_direction,
        details=dict(row.details or {}),
        schema_version=row.schema_version,
        rule_refs=list(row.rule_refs or []),
        memory_refs=list(row.memory_refs or []),
        confidence=confidence,
        warnings=list(row.warnings or []),
    )


def _serialize_point_record(point: Any) -> PointBoundaryResponse:
    return PointBoundaryResponse(
        point_id=point.point_id,
        point_ordinal=int(point.point_ordinal),
        start_video_ts_ms=int(point.start_video_ts_ms),
        end_video_ts_ms=int(point.end_video_ts_ms),
        confidence=float(point.confidence),
        boundary_evidence=list(point.boundary_evidence or []),
    )


def _video_path_for_job(job: Any) -> Path:
    if job.video_id is not None:
        transcoded = (TRANSCODED_DIR / f"{job.video_id}.mp4").resolve()
        if transcoded.exists():
            return transcoded
    if job.source_path:
        source = Path(job.source_path).resolve()
        if source.exists():
            return source
    raise FileNotFoundError(f"No playable video found for game {job.game_id}")


def create_app() -> Any:
    if FastAPI is None:
        raise RuntimeError("fastapi is not installed. Install project dependencies to use the API surface.")

    app = FastAPI(title="Sports Video Analytics API", version="0.1.0")

    @app.post("/ingest", status_code=202)
    async def ingest_endpoint(
        upload: UploadFile | None = File(default=None),
        url: str | None = Form(default=None),
        ack_rights: bool = Form(default=False),
        caller_id: str = Form(default="api"),
        game_id: str | None = Form(default=None),
        fps: int = Form(default=1),
    ) -> dict[str, Any]:
        if (upload is None and url is None) or (upload is not None and url is not None):
            raise HTTPException(
                status_code=400,
                detail="Provide exactly one source: either a file upload or a public URL.",
            )
        try:
            if upload is not None:
                saved_path = _save_upload(upload)
                job = submit_local_job(
                    saved_path,
                    game_id=game_id,
                    target_fps=fps,
                )
            else:
                assert url is not None
                job = submit_remote_job(
                    url,
                    caller_id=caller_id,
                    ack_rights=ack_rights,
                    game_id=game_id,
                    target_fps=fps,
                )
            enqueue_job(job.game_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return JobSubmissionResponse(
            job_id=job.game_id,
            game_id=job.game_id,
            status=job.status,
            stage=job.stage,
            source_kind=job.source_kind,
        ).model_dump()

    @app.get("/jobs/{job_id}")
    async def job_status_endpoint(job_id: str) -> dict[str, Any]:
        job = get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
        return JobStatusResponse(
            job_id=job.game_id,
            game_id=job.game_id,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            error_message=job.error_message,
        ).model_dump()

    @app.get("/games/{game_id}/events")
    async def game_events_endpoint(
        game_id: str,
        point_id: str | None = None,
        event_type: str | None = None,
        team: str | None = None,
    ) -> dict[str, Any]:
        job = get_job(game_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown game: {game_id}")
        rows = list_event_rows(
            game_id,
            point_id=point_id,
            event_type=event_type,
            team=team,
        )
        return GameEventsResponse(
            game_id=game_id,
            events=[_serialize_event_row(row) for row in rows],
        ).model_dump()

    @app.get("/games/{game_id}/points")
    async def game_points_endpoint(game_id: str) -> dict[str, Any]:
        job = get_job(game_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown game: {game_id}")
        return GamePointsResponse(
            game_id=game_id,
            points=[_serialize_point_record(point) for point in list_points(game_id)],
        ).model_dump()

    @app.put("/games/{game_id}/points")
    async def update_points_endpoint(
        game_id: str,
        payload: PointBoundaryUpdateRequest,
    ) -> dict[str, Any]:
        job = get_job(game_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown game: {game_id}")
        try:
            result = replace_point_boundaries(
                game_id,
                [
                    PointBoundaryPatch(
                        start_video_ts_ms=point.start_video_ts_ms,
                        end_video_ts_ms=point.end_video_ts_ms,
                    )
                    for point in payload.points
                ],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PointBoundaryUpdateResponse(
            game_id=game_id,
            points=[_serialize_point_record(point) for point in result.points],
            events_rebucketed=result.events_rebucketed,
            observations_rebucketed=result.observations_rebucketed,
        ).model_dump()

    @app.get("/games/{game_id}/video")
    async def game_video_endpoint(game_id: str) -> Any:
        job = get_job(game_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown game: {game_id}")
        try:
            video_path = _video_path_for_job(job)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        media_type = "video/mp4" if video_path.suffix.lower() == ".mp4" else "application/octet-stream"
        return FileResponse(video_path, media_type=media_type, filename=video_path.name)

    @app.post("/games/{game_id}/corrections", status_code=201)
    async def corrections_endpoint(
        game_id: str,
        payload: CorrectionCreateRequest,
    ) -> dict[str, Any]:
        job = get_job(game_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown game: {game_id}")
        try:
            result = submit_correction(
                game_id,
                CorrectionSubmission(
                    point_id=payload.point_id,
                    point_ordinal=payload.point_ordinal,
                    source_event_id=payload.source_event_id,
                    coach_id=payload.coach_id,
                    correction_type=payload.correction_type,
                    original_event=payload.original_event,
                    proposed_event=payload.proposed_event,
                    source_memory_refs=payload.source_memory_refs,
                    note=payload.note,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return CorrectionResponse(
            correction_id=result.correction_id,
            game_id=result.game_id,
            point_id=result.point_id,
            point_ordinal=result.point_ordinal,
            coach_id=result.coach_id,
            correction_type=result.correction_type,
            created_memory_ids=result.created_memory_ids,
        ).model_dump()

    @app.get("/exports/{game_id}.csv")
    async def export_events_endpoint(game_id: str) -> Any:
        job = get_job(game_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown game: {game_id}")
        return Response(content=render_events_csv(game_id), media_type="text/csv")

    return app


app = create_app() if FastAPI is not None else None

__all__ = ["UPLOAD_DIR", "app", "create_app"]
