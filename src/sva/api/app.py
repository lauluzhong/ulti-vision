"""Thin async submission and polling FastAPI surface for Phase 6."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from sva.api.contracts import JobStatusResponse, JobSubmissionResponse
from sva.jobs_dao import get_job
from sva.jobs_service import submit_local_job, submit_remote_job
from sva.queue import enqueue_job

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
except ModuleNotFoundError:  # pragma: no cover - depends on installed extras
    FastAPI = None  # type: ignore[assignment]
    File = Form = UploadFile = HTTPException = None  # type: ignore[assignment]


UPLOAD_DIR = Path("data/uploads")

def _save_upload(upload: Any) -> Path:
    suffix = Path(upload.filename or "upload.bin").suffix or ".bin"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dst = UPLOAD_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
    with dst.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return dst


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

    return app


app = create_app() if FastAPI is not None else None

__all__ = ["UPLOAD_DIR", "app", "create_app"]
