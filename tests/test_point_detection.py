"""Unit tests for the point detector — both the legacy candidate-fusion path
and the v0 detect_points_from_observations VLM-driven path."""

from __future__ import annotations

from sva.models import (
    DiscObservation,
    FieldOrientation,
    FormationObservation,
    ModelMetadata,
    Observation,
    PlayerCounts,
    SceneObservation,
)
from sva.points.detector import detect_points, detect_points_from_observations
from sva.points.types import BoundarySignal, PointBoundaryCandidate


# -------------------- Legacy candidate-fusion path --------------------


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


# -------------------- v0 VLM-driven path --------------------


def _make_observation(
    *,
    start_ms: int,
    end_ms: int,
    phase: str = "live_play",
    phase_confidence: float = 0.7,
    pull_formation_visible: bool = False,
    score_signal: str = "none",
    score_signal_confidence: float = 0.0,
    arms_raised_count: int = 0,
) -> Observation:
    return Observation(
        observation_id=f"obs_{start_ms}_{end_ms}",
        window_id=f"win_{start_ms}_{end_ms}",
        video_id="vid_test",
        video_ts_start_ms=start_ms,
        video_ts_end_ms=end_ms,
        observation_ts_ms=(start_ms + end_ms) // 2,
        scene=SceneObservation(),
        disc=DiscObservation(),
        players=PlayerCounts(),
        formation=FormationObservation(
            phase=phase,  # type: ignore[arg-type]
            phase_confidence=phase_confidence,
            pull_formation_visible=pull_formation_visible,
            arms_raised_count=arms_raised_count,
            score_signal=score_signal,  # type: ignore[arg-type]
            score_signal_confidence=score_signal_confidence,
        ),
        field_orientation=FieldOrientation(),
        model=ModelMetadata(provider="dummy", model_id="test-vlm", version="test"),
        confidence_overall=0.5,
    )


def test_detect_points_from_observations_returns_empty_for_empty_input():
    assert detect_points_from_observations("game_x", []) == []


def test_detect_points_from_observations_groups_contiguous_in_point_run():
    observations = [
        _make_observation(start_ms=0, end_ms=1000, phase="pre_pull", phase_confidence=0.6, pull_formation_visible=True),
        _make_observation(start_ms=1000, end_ms=2000, phase="live_play", phase_confidence=0.8),
        _make_observation(start_ms=2000, end_ms=3000, phase="live_play", phase_confidence=0.7),
        _make_observation(
            start_ms=3000,
            end_ms=4000,
            phase="score_celebration",
            phase_confidence=0.6,
            score_signal="two_hands_up",
            score_signal_confidence=0.7,
            arms_raised_count=3,
        ),
        _make_observation(start_ms=4000, end_ms=5000, phase="between_points", phase_confidence=0.7),
    ]

    points = detect_points_from_observations("game_alpha", observations)

    assert len(points) == 1
    pt = points[0]
    assert pt.point_id == "game_alpha:pt_001"
    assert pt.point_ordinal == 1
    assert pt.start_video_ts_ms == 0
    assert pt.end_video_ts_ms == 4000  # last in-point observation
    # Evidence captures both the pull formation AND the score signal.
    sources = sorted(signal.source for signal in pt.boundary_evidence)
    assert "pull" in sources
    assert "vlm" in sources  # score_signal=two_hands_up sources to vlm


def test_detect_points_from_observations_finds_two_points_separated_by_between_phase():
    observations = [
        # Point 1: pull -> live -> score
        _make_observation(start_ms=0, end_ms=1000, phase="pre_pull", phase_confidence=0.6, pull_formation_visible=True),
        _make_observation(start_ms=1000, end_ms=2000, phase="live_play", phase_confidence=0.8),
        _make_observation(start_ms=2000, end_ms=3000, phase="score_celebration", phase_confidence=0.6),
        # Between points
        _make_observation(start_ms=3000, end_ms=4000, phase="between_points", phase_confidence=0.7),
        _make_observation(start_ms=4000, end_ms=5000, phase="between_points", phase_confidence=0.7),
        # Point 2: pull -> live
        _make_observation(start_ms=5000, end_ms=6000, phase="pre_pull", phase_confidence=0.6, pull_formation_visible=True),
        _make_observation(start_ms=6000, end_ms=7000, phase="live_play", phase_confidence=0.8),
    ]

    points = detect_points_from_observations("game_beta", observations)

    assert len(points) == 2
    assert [p.point_ordinal for p in points] == [1, 2]
    assert points[0].point_id == "game_beta:pt_001"
    assert points[1].point_id == "game_beta:pt_002"
    assert points[0].start_video_ts_ms == 0
    assert points[0].end_video_ts_ms == 3000
    assert points[1].start_video_ts_ms == 5000
    assert points[1].end_video_ts_ms == 7000


def test_detect_points_from_observations_carries_over_unknown_phase_to_avoid_fragmentation():
    """A single noisy 'unknown' window inside a live_play run should not split
    one point into two."""
    observations = [
        _make_observation(start_ms=0, end_ms=1000, phase="live_play", phase_confidence=0.8),
        _make_observation(start_ms=1000, end_ms=2000, phase="unknown", phase_confidence=0.0),  # noise
        _make_observation(start_ms=2000, end_ms=3000, phase="live_play", phase_confidence=0.8),
    ]

    points = detect_points_from_observations("game_carryover", observations)

    assert len(points) == 1
    assert points[0].start_video_ts_ms == 0
    assert points[0].end_video_ts_ms == 3000


def test_detect_points_from_observations_falls_back_to_unclear_single_point():
    """When the VLM never produces a confident in-point phase, return one
    'unclear' point covering the whole video so the user can manually edit."""
    observations = [
        _make_observation(start_ms=0, end_ms=1000, phase="unknown", phase_confidence=0.0),
        _make_observation(start_ms=1000, end_ms=2000, phase="unknown", phase_confidence=0.0),
        _make_observation(start_ms=2000, end_ms=3000, phase="stoppage", phase_confidence=0.3),
    ]

    points = detect_points_from_observations("game_unclear", observations)

    assert len(points) == 1
    pt = points[0]
    assert pt.point_id == "game_unclear:pt_001"
    assert pt.start_video_ts_ms == 0
    assert pt.end_video_ts_ms == 3000
    assert pt.confidence < 0.2  # explicit "needs review" marker
    assert pt.boundary_evidence
    assert pt.boundary_evidence[0].details.get("fallback") == "single_point_unclear_whole_video"


def test_detect_points_from_observations_sorts_unordered_input():
    """Observations from concurrent windows may arrive out of order."""
    observations = [
        _make_observation(start_ms=2000, end_ms=3000, phase="live_play", phase_confidence=0.8),
        _make_observation(start_ms=0, end_ms=1000, phase="live_play", phase_confidence=0.8),
        _make_observation(start_ms=1000, end_ms=2000, phase="live_play", phase_confidence=0.8),
    ]

    points = detect_points_from_observations("game_sort", observations)

    assert len(points) == 1
    assert points[0].start_video_ts_ms == 0
    assert points[0].end_video_ts_ms == 3000
