"""Typed API contracts for Phase 6 routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class JobSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    game_id: str
    status: str
    stage: str
    source_kind: str | None = None


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    game_id: str
    status: str
    stage: str
    progress: dict[str, Any]
    error_message: str | None = None


__all__ = ["JobStatusResponse", "JobSubmissionResponse"]
