"""Point-boundary contracts for Phase 2."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SignalSource = Literal["scoreboard", "pull", "vlm"]


class BoundarySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: SignalSource
    video_ts_ms: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    details: dict[str, Any] = Field(default_factory=dict)


class PointBoundaryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_video_ts_ms: int = Field(ge=0)
    end_video_ts_ms: int = Field(ge=0)
    scoreboard: BoundarySignal | None = None
    pull: BoundarySignal | None = None
    vlm: BoundarySignal | None = None

    def requires_vlm_tiebreak(self) -> bool:
        scoreboard_conf = self.scoreboard.confidence if self.scoreboard is not None else 0.0
        pull_conf = self.pull.confidence if self.pull is not None else 0.0
        return scoreboard_conf < 0.6 and pull_conf < 0.6

    def has_non_vlm_anchor(self) -> bool:
        return self.scoreboard is not None or self.pull is not None


class PointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    point_id: str
    game_id: str
    point_ordinal: int = Field(ge=1)
    start_video_ts_ms: int = Field(ge=0)
    end_video_ts_ms: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    boundary_evidence: list[BoundarySignal] = Field(default_factory=list)


__all__ = [
    "BoundarySignal",
    "PointBoundaryCandidate",
    "PointRecord",
    "SignalSource",
]
