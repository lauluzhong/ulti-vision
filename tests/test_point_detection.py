"""Unit tests for the staged Phase 2 point detector."""

from __future__ import annotations

from sva.points.detector import detect_points
from sva.points.types import BoundarySignal, PointBoundaryCandidate


def test_detect_points_orders_candidates_and_uses_vlm_only_for_ambiguous_spans():
    points = detect_points(
        "game_demo",
        [
            PointBoundaryCandidate(
                start_video_ts_ms=12000,
                end_video_ts_ms=25000,
                scoreboard=BoundarySignal(source="scoreboard", video_ts_ms=12000, confidence=0.92),
                pull=BoundarySignal(source="pull", video_ts_ms=12200, confidence=0.71),
            ),
            PointBoundaryCandidate(
                start_video_ts_ms=30000,
                end_video_ts_ms=45000,
                scoreboard=BoundarySignal(source="scoreboard", video_ts_ms=30000, confidence=0.33),
                pull=BoundarySignal(source="pull", video_ts_ms=30200, confidence=0.35),
                vlm=BoundarySignal(source="vlm", video_ts_ms=30100, confidence=0.88),
            ),
        ],
    )

    assert [point.point_ordinal for point in points] == [1, 2]
    assert points[0].point_id == "game_demo:pt_001"
    assert [signal.source for signal in points[0].boundary_evidence] == ["scoreboard", "pull"]
    assert [signal.source for signal in points[1].boundary_evidence] == ["vlm"]


def test_detect_points_does_not_allow_vlm_as_whole_game_primary_signal():
    points = detect_points(
        "game_demo",
        [
            PointBoundaryCandidate(
                start_video_ts_ms=5000,
                end_video_ts_ms=12000,
                vlm=BoundarySignal(source="vlm", video_ts_ms=6000, confidence=0.95),
            )
        ],
    )

    assert points == []
