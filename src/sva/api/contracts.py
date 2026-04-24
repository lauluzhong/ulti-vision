"""Typed API contracts for Phase 6 routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class EventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    game_id: str
    point_id: str
    point_ordinal: int
    video_ts_ms: int
    in_point_ts_ms: int
    type: str
    team: str
    turnover_subtype: str | None = None
    throw_type: str | None = None
    pass_direction: str | None = None
    details: dict[str, Any]
    schema_version: str
    rule_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)


class GameEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: str
    events: list[EventResponse]


class CorrectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    point_id: str = Field(min_length=1)
    point_ordinal: int = Field(ge=1)
    source_event_id: str | None = None
    coach_id: str = Field(min_length=1)
    correction_type: str
    original_event: dict[str, Any] = Field(default_factory=dict)
    proposed_event: dict[str, Any] = Field(default_factory=dict)
    source_memory_refs: list[str] = Field(default_factory=list)
    note: str = ""

    @field_validator("point_id", "coach_id", "correction_type")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("source_event_id")
    @classmethod
    def _strip_optional_event_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _validate_payload_shape(self) -> "CorrectionCreateRequest":
        requires_source = {"flag_wrong", "reclassify", "delete_spurious"}
        requires_proposed = {"reclassify", "mark_missed"}
        if self.correction_type in requires_source and not self.source_event_id:
            raise ValueError(f"{self.correction_type} requires source_event_id")
        if self.correction_type in requires_proposed and not self.proposed_event:
            raise ValueError(f"{self.correction_type} requires proposed_event")
        return self


class CorrectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correction_id: str
    game_id: str
    point_id: str
    point_ordinal: int
    coach_id: str
    correction_type: str
    created_memory_ids: list[str] = Field(default_factory=list)


__all__ = [
    "CorrectionCreateRequest",
    "CorrectionResponse",
    "EventResponse",
    "GameEventsResponse",
    "JobStatusResponse",
    "JobSubmissionResponse",
]
