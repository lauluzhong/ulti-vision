"""Thin synchronous FastAPI ingest surface for Phase 2."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sva.ingest import LocalFileSource, RemoteUrlSource, SourcePolicyError, ingest_source

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
except ModuleNotFoundError:  # pragma: no cover - depends on installed extras
    FastAPI = None  # type: ignore[assignment]
    File = Form = UploadFile = HTTPException = None  # type: ignore[assignment]


UPLOAD_DIR = Path("data/uploads")


def _serialize_ingest_result(result: Any) -> dict[str, Any]:
    payload = asdict(result)
    payload["source_metadata"] = result.source_metadata.model_dump()
    payload["transcoded_metadata"] = result.transcoded_metadata.model_dump()
    return payload


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

    @app.post("/ingest")
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
                result = ingest_source(
                    LocalFileSource(path=str(saved_path)),
                    game_id=game_id,
                    target_fps=fps,
                )
            else:
                assert url is not None
                result = ingest_source(
                    RemoteUrlSource(url=url, ack_rights=ack_rights, caller_id=caller_id),
                    game_id=game_id,
                    target_fps=fps,
                )
        except SourcePolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return _serialize_ingest_result(result)

    return app


app = create_app() if FastAPI is not None else None

__all__ = ["UPLOAD_DIR", "app", "create_app"]
