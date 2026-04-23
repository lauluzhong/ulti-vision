"""Swap-safe Pydantic contracts shared across the ingest -> perceive -> interpret -> memory pipeline.

All models are VLM/LLM-agnostic. See .planning/research/ARCHITECTURE.md §Swap-Safety Contracts
for the full rationale. The `schema_version` field is mandatory on every top-level model so
downstream caches (Phase 3 per-window cache, Phase 5 memory re-embed) can key by it.

Lives as a single flat module per CONTEXT D-04. Split into a package only if it exceeds ~300 lines.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["1.0"] = "1.0"

EventType = Literal[
    "possession_start",
    "possession_end",
    "completion",
    "turnover",
    "goal",
    "point_end",
    "unknown",
]
Team = Literal["dark", "light", "none", "unknown"]
FieldVisible = Literal["full", "partial", "none"]
Camera = Literal["sideline", "endzone", "elevated", "handheld", "unknown"]
Lighting = Literal["ok", "harsh", "dim"]
PossessorRole = Literal["thrower", "receiver", "defender", "none"]
MemoryKind = Literal["few_shot_positive", "few_shot_negative", "rule", "correction"]


class ModelMetadata(BaseModel):
    """Provider-neutral model identifier attached to every VLM/LLM output."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    provider: str                     # e.g. "gemini", "anthropic", "qwen"
    model_id: str                     # e.g. "gemini-2.5-flash", "claude-sonnet-4-5"
    version: str                      # adapter-reported version string


class SceneObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_visible: FieldVisible = "none"
    camera: Camera = "unknown"
    lighting: Lighting = "ok"
    obstruction: bool = False


class DiscObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visible: bool = False
    in_air: bool = False
    possessor_team: Team = "unknown"
    possessor_role: PossessorRole = "none"


class PlayerCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dark_count_visible: int = 0
    light_count_visible: int = 0


class ActionTag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str
    confidence: float = Field(ge=0.0, le=1.0)


class TextObserved(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    kind: Literal["scoreboard", "jersey", "other"] = "other"
    confidence: float = Field(ge=0.0, le=1.0)


class Observation(BaseModel):
    """VLM-produced structured observation for one sampled window. Swap-safe by construction."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    observation_id: str
    window_id: str
    video_id: str
    video_ts_start_ms: int = Field(ge=0)
    video_ts_end_ms: int = Field(ge=0)
    observation_ts_ms: int = Field(ge=0)
    scene: SceneObservation = Field(default_factory=SceneObservation)
    disc: DiscObservation = Field(default_factory=DiscObservation)
    players: PlayerCounts = Field(default_factory=PlayerCounts)
    actions_detected: list[ActionTag] = Field(default_factory=list)
    text_observed: list[TextObserved] = Field(default_factory=list)
    free_form_note: str = ""
    model: ModelMetadata
    confidence_overall: float = Field(ge=0.0, le=1.0)
    raw_response_ref: str | None = None


class Event(BaseModel):
    """Canonical per-point output. LLM adapters produce this; UI/export consume this."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: str
    game_id: str
    point_id: str
    point_ordinal: int = Field(ge=1)
    video_ts_ms: int = Field(ge=0)
    in_point_ts_ms: int = Field(ge=0)
    type: EventType
    team: Team = "unknown"
    player_id: None = None                    # v1 contract — always None (PROJECT.md key decision)
    details: dict[str, Any] = Field(default_factory=dict)
    source_observations: list[str] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    warnings: list[str] = Field(default_factory=list)
    corrected_from_event_id: str | None = None
    model: ModelMetadata


class MemorySource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Literal["seed", "correction", "eval", "manual"] = "manual"
    source_coach_id: str | None = None
    source_correction_id: str | None = None
    source_event_id: str | None = None


class MemoryRecord(BaseModel):
    """Model-agnostic memory row. Swapping VLM/LLM must not invalidate these rows."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    memory_id: str
    kind: MemoryKind
    tags: list[str] = Field(default_factory=list)
    scope: str = "global"                     # "global" | "coach:<id>" | "team:<id>"
    source: MemorySource = Field(default_factory=MemorySource)
    embedding_ref: str | None = None
    embedding_input: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    corroborations: int = Field(ge=0, default=0)
    created_at: datetime
    last_used_at: datetime | None = None


__all__ = [
    "SCHEMA_VERSION",
    "Observation",
    "Event",
    "MemoryRecord",
    "ModelMetadata",
    "SceneObservation",
    "DiscObservation",
    "PlayerCounts",
    "ActionTag",
    "TextObserved",
    "MemorySource",
    "EventType",
    "Team",
]
