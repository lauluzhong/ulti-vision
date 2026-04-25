"""Deterministic point-aware event metrics for Phase 7."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict

from sva.eval.gold import ComparableEvent

DEFAULT_TOLERANCE_MS = {
    "completion": 3000,
    "turnover": 3000,
    "goal": 5000,
    "possession_start": 5000,
    "possession_end": 5000,
    "point_end": 5000,
    "unknown": 5000,
}


class EventMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gold_count: int
    predicted_count: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None


def _tolerance_for(event_type: str) -> int:
    return DEFAULT_TOLERANCE_MS.get(event_type, 5000)


def compute_event_metrics(
    gold_events: list[ComparableEvent],
    predicted_events: list[ComparableEvent],
) -> dict[str, EventMetric]:
    unmatched_predictions = set(range(len(predicted_events)))
    true_positives_by_type: dict[str, int] = defaultdict(int)

    for gold in sorted(gold_events, key=lambda event: (event.game_id, event.point_id, event.video_ts_ms)):
        tolerance = _tolerance_for(gold.type)
        candidates: list[tuple[int, int]] = []
        for index, predicted in enumerate(predicted_events):
            if index not in unmatched_predictions:
                continue
            if predicted.game_id != gold.game_id:
                continue
            if predicted.point_id != gold.point_id:
                continue
            if predicted.type != gold.type:
                continue
            if predicted.team != gold.team:
                continue
            distance = abs(predicted.video_ts_ms - gold.video_ts_ms)
            if distance <= tolerance:
                candidates.append((distance, index))
        if not candidates:
            continue
        _, best_index = min(candidates, key=lambda item: (item[0], item[1]))
        unmatched_predictions.remove(best_index)
        true_positives_by_type[gold.type] += 1

    gold_count_by_type: dict[str, int] = defaultdict(int)
    predicted_count_by_type: dict[str, int] = defaultdict(int)
    for event in gold_events:
        gold_count_by_type[event.type] += 1
    for event in predicted_events:
        predicted_count_by_type[event.type] += 1

    all_types = sorted(set(gold_count_by_type) | set(predicted_count_by_type))
    metrics: dict[str, EventMetric] = {}
    for event_type in all_types:
        gold_count = gold_count_by_type.get(event_type, 0)
        predicted_count = predicted_count_by_type.get(event_type, 0)
        true_positives = true_positives_by_type.get(event_type, 0)
        false_positives = predicted_count - true_positives
        false_negatives = gold_count - true_positives
        precision = None if predicted_count == 0 else round(true_positives / predicted_count, 3)
        recall = None if gold_count == 0 else round(true_positives / gold_count, 3)
        metrics[event_type] = EventMetric(
            gold_count=gold_count,
            predicted_count=predicted_count,
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            precision=precision,
            recall=recall,
        )
    return metrics


def aggregate_metrics(
    metrics_by_type: dict[str, EventMetric],
    event_types: tuple[str, ...],
) -> EventMetric | None:
    selected = [metrics_by_type[event_type] for event_type in event_types if event_type in metrics_by_type]
    if not selected:
        return None
    gold_count = sum(metric.gold_count for metric in selected)
    predicted_count = sum(metric.predicted_count for metric in selected)
    true_positives = sum(metric.true_positives for metric in selected)
    false_positives = predicted_count - true_positives
    false_negatives = gold_count - true_positives
    precision = None if predicted_count == 0 else round(true_positives / predicted_count, 3)
    recall = None if gold_count == 0 else round(true_positives / gold_count, 3)
    return EventMetric(
        gold_count=gold_count,
        predicted_count=predicted_count,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
    )


__all__ = ["EventMetric", "aggregate_metrics", "compute_event_metrics"]
