"""Swap-safe Pydantic contracts shared across the ingest -> perceive -> interpret -> memory pipeline.

All models are VLM/LLM-agnostic. See .planning/research/ARCHITECTURE.md §Swap-Safety Contracts
for the full rationale. The `schema_version` field is mandatory on every top-level model so
downstream caches (Phase 3 per-window cache, Phase 5 memory re-embed) can key by it.

OBSERVATION SCHEMA v2.0 — DETERMINISTIC FACT-OUTPUT DESIGN
=========================================================

Architectural principle (locked in 2026-05-01):

    The VLM is a DETERMINISTIC OBSERVER. It reports facts about a single 2-second
    window. It does NOT interpret, deduce, or infer.

    The LLM is the DEDUCER. It reasons across the window timeline applying WFDF
    rules and accumulated memory.

Implications:
- Every VLM-produced field is a yes/no fact (or a categorical fact) plus a
  confidence. No "free-form notes" as primary signal.
- Where two windows would naturally need stitching (e.g., "did this throw
  complete?"), each window reports its OWN observable fact (throw_release in
  window N, catch_completed in window N+1). The LLM stitches.
- "Role" is not a VLM concept. We do not ask "is this player a thrower or a
  receiver?" — that's interpretation. The VLM just reports observable state:
  who is in contact with the disc, where is the disc, where is the field.
- Schema bumped to "2.0". Cached observations from "1.0" are no longer valid;
  the prompt_version_hash naturally invalidates them on the next run.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# -----------------------------------------------------------------------------
# Categorical types
# -----------------------------------------------------------------------------

SCHEMA_VERSION: Literal["2.0"] = "2.0"

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
MemoryKind = Literal["few_shot_positive", "few_shot_negative", "rule", "correction"]
CorrectionType = Literal["flag_wrong", "reclassify", "mark_missed", "delete_spurious"]
DiscVisibilityQuality = Literal["clear", "blurry", "likely_present_not_visible", "absent"]
TurnoverSubtype = Literal["throwaway", "drop", "block", "interception", "out_of_bounds", "unknown"]
ThrowType = Literal["forehand", "backhand", "hammer", "blade", "unknown"]
PassDirection = Literal["up-field", "down-field", "lateral", "unknown"]

GamePhase = Literal[
    "pre_pull",                 # 7 defenders lined on endzone, offense lined on opposite endzone, awaiting release
    "pull_in_air",              # disc is in flight after the pull throw, both lines moving
    "live_play",                # standard offense vs defense, possession contested or held
    "post_score_celebration",   # offense in attacking endzone, possible arms-up signal
    "between_points",           # players walking back to lines, no active play
    "stoppage",                 # discussion / call / timeout
    "unknown",
]

DiscMotionDirection = Literal[
    "left_to_right",
    "right_to_left",
    "top_to_bottom",            # toward the bottom of the frame
    "bottom_to_top",            # toward the top of the frame
    "diagonal_up_right",
    "diagonal_up_left",
    "diagonal_down_right",
    "diagonal_down_left",
    "mostly_stationary",
    "unclear",
]


# -----------------------------------------------------------------------------
# Provider-neutral metadata
# -----------------------------------------------------------------------------


class ModelMetadata(BaseModel):
    """Provider-neutral model identifier attached to every VLM/LLM output."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    provider: str                     # e.g. "gemini", "anthropic", "qwen"
    model_id: str                     # e.g. "gemini-2.5-flash", "claude-sonnet-4-5"
    version: str                      # adapter-reported version string


# -----------------------------------------------------------------------------
# v2.0 Observation sub-models — pure factual observations
# -----------------------------------------------------------------------------


class SceneObservation(BaseModel):
    """Setting / camera / lighting facts about this window."""

    model_config = ConfigDict(extra="forbid")
    field_visible: FieldVisible = "none"
    camera: Camera = "unknown"
    lighting: Lighting = "ok"
    obstruction: bool = False
    multiple_discs_possible: bool = False


class DiscState(BaseModel):
    """Where the disc IS, observably. No role inference, no interpretation.

    A disc can simultaneously be `visible=true`, `held_by_player=true`, and
    `on_ground=false` (held disc) — or `visible=true, in_air=true, held=false,
    on_ground=false` (mid-flight). All three boolean states (in_air, on_ground,
    held_by_player) describe orthogonal-ish physical states; the VLM picks
    whichever is most accurate.
    """

    model_config = ConfigDict(extra="forbid")
    visible: bool = False
    visibility_quality: DiscVisibilityQuality = "absent"
    in_air: bool = False
    on_ground: bool = False
    held_by_player: bool = False
    state_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class DiscPosition(BaseModel):
    """Approximate disc position in the camera frame, normalized 0-1.

    x_norm: 0 = left edge, 1 = right edge.
    y_norm: 0 = top edge,  1 = bottom edge.

    Both are nullable — the VLM reports None if it can't reasonably ballpark
    the position. Confidence 0 if either field is None.
    """

    model_config = ConfigDict(extra="forbid")
    x_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    y_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class DiscPossessor(BaseModel):
    """Which team is in contact with the disc this window, if any.

    Note: we do NOT ask "is this player a thrower or a receiver?" — that's
    interpretation. We just record team color and (if visible) jersey number.
    The LLM derives role from cross-window context.
    """

    model_config = ConfigDict(extra="forbid")
    team: Team = "unknown"
    team_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    jersey_number: str | None = None
    jersey_number_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class DiscMotion(BaseModel):
    """Did the disc move within this window's frames? Which way (in-frame)?

    Cumulative direction across a point is the LLM's job; we only report
    per-window in-frame motion. fps>=2 inside the window is required for this
    to be reliable; the perceiver sets video_metadata.fps explicitly.
    """

    model_config = ConfigDict(extra="forbid")
    moved_significantly: bool = False
    direction: DiscMotionDirection = "unclear"
    direction_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class FieldGeometry(BaseModel):
    """Where the field landmarks ARE in the frame.

    "near" / "far" are relative to the camera: an endzone closer to the camera
    is "near", an endzone deeper into the frame is "far". This works for
    sideline cameras (most common). For elevated / endzone cameras both
    near/far may be visible.
    """

    model_config = ConfigDict(extra="forbid")
    endzone_near_visible: bool = False
    endzone_near_x_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    endzone_far_visible: bool = False
    endzone_far_x_norm: float | None = Field(default=None, ge=0.0, le=1.0)
    sideline_left_visible: bool = False
    sideline_right_visible: bool = False
    geometry_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class ScoreboardReading(BaseModel):
    """OCR of any visible scoreboard. Per-team scores extracted as integers
    when readable; clock kept as raw text since formatting varies."""

    model_config = ConfigDict(extra="forbid")
    visible: bool = False
    dark_team_score: int | None = Field(default=None, ge=0)
    light_team_score: int | None = Field(default=None, ge=0)
    clock_text: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class WindowEvents(BaseModel):
    """Discrete events the VLM observed within this window. Each is a
    yes/no fact with confidence — multiple may fire simultaneously
    (e.g., a throw_release in the first half of the window plus a
    catch_completed in the second half if the window straddles a short
    pass).
    """

    model_config = ConfigDict(extra="forbid")

    # Throw initiation: disc transitioned from held -> in_air
    throw_release_observed: bool = False
    throw_release_team: Team = "unknown"          # team that was holding before release
    throw_release_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Catch: disc transitioned from in_air -> held_by_player by the SAME team
    catch_completed_observed: bool = False
    catch_team: Team = "unknown"
    catch_completed_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Drop: disc went in_air -> on_ground without being caught
    drop_observed: bool = False
    drop_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Block: a defender clearly contacted the disc mid-flight
    block_observed: bool = False
    block_defender_team: Team = "unknown"
    block_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Interception: disc went in_air -> held_by_player by the OPPOSITE team
    interception_observed: bool = False
    interception_team: Team = "unknown"            # the team that intercepted
    interception_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Out of bounds: disc crossed a sideline or back endzone line
    out_of_bounds_observed: bool = False
    out_of_bounds_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Layout: any player visibly diving full-body horizontally
    layout_observed: bool = False
    layout_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # Score signal: someone with both arms straight overhead (WFDF goal call)
    arms_raised_score_signal_observed: bool = False
    arms_raised_count: int = Field(ge=0, default=0)
    arms_raised_score_signal_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class FormationObservation(BaseModel):
    """Overall game phase for this window. Used by the point detector.

    Phase IS partially interpretive but is structurally aligned with Ultimate's
    flow (pull / play / score / between) and is needed for point boundaries.
    Kept intentionally coarse.
    """

    model_config = ConfigDict(extra="forbid")
    phase: GamePhase = "unknown"
    phase_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    pull_formation_visible: bool = False        # 7 defenders on an endzone line


class PlayerCounts(BaseModel):
    """How many players are visible this window, broken out by team and by
    end-zone occupancy (for goal detection)."""

    model_config = ConfigDict(extra="forbid")
    dark_count_visible: int = Field(ge=0, default=0)
    light_count_visible: int = Field(ge=0, default=0)
    in_endzone_near: int = Field(ge=0, default=0)
    in_endzone_far: int = Field(ge=0, default=0)


class TextObserved(BaseModel):
    """Free-form OCR for non-scoreboard text (jerseys, sideline signs, etc).

    Scoreboard text is captured separately and structurally in
    ScoreboardReading; this list is for things the schema doesn't encode.
    """

    model_config = ConfigDict(extra="forbid")
    text: str
    kind: Literal["jersey", "other"] = "other"
    confidence: float = Field(ge=0.0, le=1.0)


# -----------------------------------------------------------------------------
# v2.0 Observation — top-level fact bundle for one 2-sec window
# -----------------------------------------------------------------------------


class Observation(BaseModel):
    """VLM-produced structured observation for one sampled window. Swap-safe by construction.

    v2.0: deterministic-fact design. Every interpretive field has been replaced
    with observable yes/no facts plus confidence. Free-form notes demoted to
    `debug_note` (NOT used as primary signal by the LLM).
    """

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    observation_id: str
    window_id: str
    video_id: str
    video_ts_start_ms: int = Field(ge=0)
    video_ts_end_ms: int = Field(ge=0)
    observation_ts_ms: int = Field(ge=0)

    scene: SceneObservation = Field(default_factory=SceneObservation)
    disc: DiscState = Field(default_factory=DiscState)
    disc_position: DiscPosition = Field(default_factory=DiscPosition)
    disc_possessor: DiscPossessor = Field(default_factory=DiscPossessor)
    disc_motion: DiscMotion = Field(default_factory=DiscMotion)
    field_geometry: FieldGeometry = Field(default_factory=FieldGeometry)
    scoreboard: ScoreboardReading = Field(default_factory=ScoreboardReading)
    events: WindowEvents = Field(default_factory=WindowEvents)
    formation: FormationObservation = Field(default_factory=FormationObservation)
    players: PlayerCounts = Field(default_factory=PlayerCounts)
    text_observed: list[TextObserved] = Field(default_factory=list)

    debug_note: str = ""
    """Demoted from free_form_note. Debugging only. The LLM ignores this for
    primary inference; we keep it for human-in-the-loop visual checks."""

    model: ModelMetadata
    confidence_overall: float = Field(ge=0.0, le=1.0)
    raw_response_ref: str | None = None


# -----------------------------------------------------------------------------
# Event — LLM-deduced canonical event row (unchanged from v1.0; still 2.0
# carries forward via the schema_version literal)
# -----------------------------------------------------------------------------


class Event(BaseModel):
    """Canonical per-point output. LLM adapters produce this; UI/export consume this."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["2.0"] = SCHEMA_VERSION
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


# -----------------------------------------------------------------------------
# Memory + corrections (unchanged from v1.0; still keyed by schema_version)
# -----------------------------------------------------------------------------


class MemorySource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Literal["seed", "correction", "eval", "manual"] = "manual"
    source_coach_id: str | None = None
    source_correction_id: str | None = None
    source_event_id: str | None = None


class MemoryRecord(BaseModel):
    """Model-agnostic memory row. Swapping VLM/LLM must not invalidate these rows."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["2.0"] = SCHEMA_VERSION
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
    schema_version: Literal["2.0"] = SCHEMA_VERSION
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


# -----------------------------------------------------------------------------
# Backward-compat aliases (v1.0 -> v2.0). Test fixtures historically used these
# names. They map to the closest v2.0 equivalent so default-construction
# (e.g. `disc=DiscObservation()`) still works.
# Remove once all callers migrate.
# -----------------------------------------------------------------------------

DiscObservation = DiscState
FieldOrientation = FieldGeometry


__all__ = [
    "SCHEMA_VERSION",
    "Observation",
    "Event",
    "MemoryRecord",
    "CorrectionRecord",
    "ModelMetadata",
    # Observation sub-models
    "SceneObservation",
    "DiscState",
    "DiscPosition",
    "DiscPossessor",
    "DiscMotion",
    "FieldGeometry",
    "ScoreboardReading",
    "WindowEvents",
    "FormationObservation",
    "PlayerCounts",
    "TextObserved",
    # Categorical types
    "MemorySource",
    "EventType",
    "Team",
    "CorrectionType",
    "DiscVisibilityQuality",
    "TurnoverSubtype",
    "ThrowType",
    "PassDirection",
    "GamePhase",
    "DiscMotionDirection",
    "FieldVisible",
    "Camera",
    "Lighting",
    "MemoryKind",
    # Backward-compat aliases (v1.0 names -> v2.0 types)
    "DiscObservation",
    "FieldOrientation",
]
