"""Unit tests for Phase 7 per-event metrics."""

from __future__ import annotations

def test_compute_event_metrics_is_per_type_and_point_aware():
    from sva.eval.gold import ComparableEvent
    from sva.eval.metrics import compute_event_metrics

    gold = [
        ComparableEvent(
            game_id="game_a",
            point_id="game_a:pt_001",
            point_ordinal=1,
            video_ts_ms=1000,
            in_point_ts_ms=1000,
            type="completion",
            team="dark",
        ),
        ComparableEvent(
            game_id="game_a",
            point_id="game_a:pt_002",
            point_ordinal=2,
            video_ts_ms=5000,
            in_point_ts_ms=1000,
            type="goal",
            team="light",
        ),
    ]
    predicted = [
        ComparableEvent(
            game_id="game_a",
            point_id="game_a:pt_001",
            point_ordinal=1,
            video_ts_ms=1200,
            in_point_ts_ms=1200,
            type="completion",
            team="dark",
        ),
        ComparableEvent(
            game_id="game_a",
            point_id="game_a:pt_009",
            point_ordinal=9,
            video_ts_ms=5200,
            in_point_ts_ms=1200,
            type="goal",
            team="light",
        ),
    ]

    metrics = compute_event_metrics(gold, predicted)

    assert set(metrics) == {"completion", "goal"}
    assert metrics["completion"].true_positives == 1
    assert metrics["completion"].precision == 1.0
    assert metrics["completion"].recall == 1.0
    assert metrics["goal"].true_positives == 0
    assert metrics["goal"].false_negatives == 1
    assert metrics["goal"].false_positives == 1
