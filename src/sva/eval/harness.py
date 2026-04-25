"""Eval harness and honest readiness reporting for Phase 7."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sva.eval.gold import ComparableEvent, GoldManifest, load_gold_manifest
from sva.eval.metrics import EventMetric, aggregate_metrics, compute_event_metrics
from sva.events_dao import list_event_rows


class EvalPrediction(ComparableEvent):
    event_id: str | None = None


class AlphaGateStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    completion_recall: float | None = None
    completion_precision: float | None = None
    goal_recall: float | None = None
    possession_change_recall: float | None = None


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    dataset_ready: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    full_games_total: int
    points_total: int
    independent_annotation_complete: bool
    metrics_by_type: dict[str, EventMetric]
    alpha_gate: AlphaGateStatus


def _prediction_from_row(row: Any) -> EvalPrediction:
    return EvalPrediction(
        event_id=getattr(row, "event_id", None),
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
    )


def load_predictions(path: str | Path) -> list[EvalPrediction]:
    payload = json.loads(Path(path).read_text())
    rows = payload["events"] if isinstance(payload, dict) else payload
    return [EvalPrediction.model_validate(row) for row in rows]


def _dataset_ready(manifest: GoldManifest) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if manifest.full_games_total() < manifest.minimum_full_games:
        reasons.append(
            f"need at least {manifest.minimum_full_games} full games, found {manifest.full_games_total()}"
        )
    if manifest.points_total() < manifest.minimum_points:
        reasons.append(
            f"need at least {manifest.minimum_points} labeled points, found {manifest.points_total()}"
        )
    if not manifest.independent_annotation_complete():
        reasons.append("independent annotator metadata is incomplete")
    return (not reasons, reasons)


def _alpha_gate(metrics_by_type: dict[str, EventMetric], dataset_ready: bool, reasons: list[str]) -> AlphaGateStatus:
    completion = metrics_by_type.get("completion")
    goal = metrics_by_type.get("goal")
    possession_change = aggregate_metrics(metrics_by_type, ("possession_start", "possession_end"))

    blocked_reasons = list(reasons)
    if completion is None:
        blocked_reasons.append("missing completion metrics")
    if goal is None:
        blocked_reasons.append("missing goal metrics")
    if possession_change is None:
        blocked_reasons.append("missing possession-change metrics")

    completion_recall = None if completion is None else completion.recall
    completion_precision = None if completion is None else completion.precision
    goal_recall = None if goal is None else goal.recall
    possession_change_recall = None if possession_change is None else possession_change.recall

    ready = dataset_ready
    ready = ready and completion_recall is not None and completion_recall >= 0.85
    ready = ready and completion_precision is not None and completion_precision >= 0.70
    ready = ready and goal_recall is not None and goal_recall >= 0.95
    ready = ready and possession_change_recall is not None and possession_change_recall >= 0.95
    return AlphaGateStatus(
        ready=ready,
        blocked_reasons=blocked_reasons,
        completion_recall=completion_recall,
        completion_precision=completion_precision,
        goal_recall=goal_recall,
        possession_change_recall=possession_change_recall,
    )


def run_eval(
    gold_manifest_path: str | Path,
    *,
    predictions_path: str | Path | None = None,
) -> EvalReport:
    manifest = load_gold_manifest(gold_manifest_path)
    dataset_ready, reasons = _dataset_ready(manifest)
    if predictions_path is None:
        predictions = [
            _prediction_from_row(row)
            for game in manifest.games
            for row in list_event_rows(game.game_id)
        ]
    else:
        predictions = load_predictions(predictions_path)
    metrics = compute_event_metrics(manifest.events, predictions)
    alpha_gate = _alpha_gate(metrics, dataset_ready, reasons)
    return EvalReport(
        dataset_id=manifest.dataset_id,
        dataset_ready=dataset_ready,
        blocking_reasons=reasons,
        full_games_total=manifest.full_games_total(),
        points_total=manifest.points_total(),
        independent_annotation_complete=manifest.independent_annotation_complete(),
        metrics_by_type=metrics,
        alpha_gate=alpha_gate,
    )


__all__ = ["AlphaGateStatus", "EvalPrediction", "EvalReport", "load_predictions", "run_eval"]
