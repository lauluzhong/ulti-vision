"""Gold-set contracts and manifest loading for Phase 7."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sva.models import EventType, PassDirection, Team, ThrowType, TurnoverSubtype


class ComparableEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: str
    point_id: str
    point_ordinal: int = Field(ge=1)
    video_ts_ms: int = Field(ge=0)
    in_point_ts_ms: int = Field(ge=0)
    type: EventType
    team: Team = "unknown"
    turnover_subtype: TurnoverSubtype | None = None
    throw_type: ThrowType | None = None
    pass_direction: PassDirection | None = None


class GoldEvent(ComparableEvent):
    gold_event_id: str
    labeler_id: str
    notes: str = ""

    @field_validator("gold_event_id", "labeler_id")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class GoldGame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: str
    source_video_ref: str
    is_full_game: bool = True
    builder_labeler_id: str
    independent_annotator_id: str | None = None
    notes: str = ""

    @field_validator("game_id", "source_video_ref", "builder_labeler_id")
    @classmethod
    def _strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("independent_annotator_id")
    @classmethod
    def _strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def _validate_annotators(self) -> "GoldGame":
        if self.independent_annotator_id == self.builder_labeler_id:
            raise ValueError("independent_annotator_id must differ from builder_labeler_id")
        return self


class GoldManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    minimum_full_games: int = Field(default=3, ge=1)
    minimum_points: int = Field(default=40, ge=1)
    games: list[GoldGame]
    events: list[GoldEvent]

    @field_validator("dataset_id")
    @classmethod
    def _strip_dataset_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("dataset_id must not be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_cross_refs(self) -> "GoldManifest":
        game_ids = [game.game_id for game in self.games]
        if len(game_ids) != len(set(game_ids)):
            raise ValueError("game_id values must be unique inside games")
        unknown_games = sorted({event.game_id for event in self.events if event.game_id not in set(game_ids)})
        if unknown_games:
            raise ValueError(f"events reference unknown games: {', '.join(unknown_games)}")
        return self

    def full_games_total(self) -> int:
        return sum(1 for game in self.games if game.is_full_game)

    def points_total(self) -> int:
        return len({(event.game_id, event.point_id) for event in self.events})

    def independent_annotation_complete(self) -> bool:
        return all(game.independent_annotator_id is not None for game in self.games)


def load_gold_manifest(path: str | Path) -> GoldManifest:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text())
    return GoldManifest.model_validate(payload)


__all__ = [
    "ComparableEvent",
    "GoldEvent",
    "GoldGame",
    "GoldManifest",
    "load_gold_manifest",
]
