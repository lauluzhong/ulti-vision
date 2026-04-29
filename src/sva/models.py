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
CorrectionType = Literal["flag_wrong", "reclassify", "mark_missed", "delete_spurious"]
DiscVisibilityQuality = Literal["clear", "blurry", "likely_present_not_visible", "absent"]
TurnoverSubtype = Literal["throwaway", "drop", "block", "out_of_bounds", "unknown"]
ThrowType = Literal["forehand", "backhand", "hammer", "blade", "unknown"]
PassDirection = Literal["up-field", "down-field", "lateral", "unknown"]

# v0 point-detection enums — VLM populates these so the heuristic point detector
# can find pull formations and score signals without re-running the LLM.
GamePhase = Literal[
    "pre_pull",        # 7 defenders lined on endzone, offense lined on opposite endzone, awaiting release
    "pull_in_air",     # disc has been pulled, both lines in motion
    "live_play",       # standard offense vs defense, possession contested or held
    "score_celebration",  # offense in attacking endzone, possible score signal from sideline
    "between_points",  # players walking back to lines, no active play
    "stoppage",        # discussion / call / timeout
    "unknown",
]
ScoreSignal = Literal[
    "two_hands_up",    # WFDF-style "goal scored" signal — straight arms overhead
    "scoreboard_change",  # OCR detected a tick on the scoreboard since last window
    "none",
    "unknown",
]
ScoringDirection = Literal[
    "screen_left",     # offense attacking left edge of frame
    "screen_right",    # offense attacking right edge of frame
    "screen_far",      # attacking the back of the frame (camera behind defense)
    "screen_near",     # attacking the front of the frame (camera behind offense)
    "unclear",
    "unknown",
]


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
    multiple_discs_possible: bool = False


class DiscObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visible: bool = False
    visibility_quality: DiscVisibilityQuality = "absent"
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


class FormationObservation(BaseModel):
    """Ultimate-specific formation cues used by the point detector.

    v0 contract: capture only what's visible in the window. Default to unknown when
    the VLM can't tell (don't fabricate). The point detector reads these to find
    point boundaries WITHOUT having to re-prompt the LLM.
    """

    model_config = ConfigDict(extra="forbid")
    phase: GamePhase = "unknown"
    phase_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    pull_formation_visible: bool = False
    """True if 7 defenders are visibly lined up on one endzone awaiting the pull release."""
    arms_raised_count: int = Field(ge=0, default=0)
    """Count of distinct people in frame with both arms raised straight overhead.
    A goal signal in WFDF is two straight arms up; multiple people often signal together
    after a score. The LLM can use the count + phase to infer scoring."""
    score_signal: ScoreSignal = "none"
    score_signal_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class FieldOrientation(BaseModel):
    """Where the field is in the frame and which way the offense is attacking.

    v0 contract: VLM reports best-effort. The pipeline gates 'pass_direction'
    on this being known so we don't fabricate up-field/down-field.
    """

    model_config = ConfigDict(extra="forbid")
    scoring_direction: ScoringDirection = "unknown"
    """Direction the team in possession is attacking, relative to camera frame."""
    endzone_visible: Literal["near", "far", "both", "neither", "unknown"] = "unknown"
    """Whether an endzone line is visible in this window — needed to confirm goals."""
    centerline_x_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    """Approximate x-coordinate (0=left edge, 1=right edge) of the disc's current
    field-x position, when derivable from visible field lines. None if unclear."""


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
    formation: FormationObservation = Field(default_factory=FormationObservation)
    """v0: Ultimate-specific formation cues. Drives the heuristic point detector."""
    field_orientation: FieldOrientation = Field(default_factory=FieldOrientation)
    """v0: where the field is in frame, which way offense is attacking. Gates pass_direction."""
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
    turnover_subtype: TurnoverSubtype | None = None
    throw_type: ThrowType | None = None
    pass_direction: PassDirection | None = None
    prompt_version_hash: str | None = None
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


class CorrectionRecord(BaseModel):
    """Immutable coach correction row used to derive memory safely."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    correction_id: str
    game_id: str
    point_id: str
    point_ordinal: int = Field(ge=1)
    source_event_id: str | None = None
    coach_id: str
    correction_type: CorrectionType
    original_event: dict[str, Any] = Field(default_factory=dict)
    proposed_event: dict[str, Any] = Field(default_factory=dict)
    source_memory_refs: list[str] = Field(default_factory=list)
    note: str = ""
    created_at: datetime


__all__ = [
    "SCHEMA_VERSION",
    "Observation",
    "Event",
    "MemoryRecord",
    "CorrectionRecord",
    "ModelMetadata",
    "SceneObservation",
    "DiscObservation",
    "PlayerCounts",
    "ActionTag",
    "TextObserved",
    "FormationObservation",
    "FieldOrientation",
    "MemorySource",
    "EventType",
    "Team",
    "CorrectionType",
    "DiscVisibilityQuality",
    "TurnoverSubtype",
    "ThrowType",
    "PassDirection",
    "GamePhase",
    "ScoreSignal",
    "ScoringDirection",
]
