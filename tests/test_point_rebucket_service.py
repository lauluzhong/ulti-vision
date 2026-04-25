"""Focused unit tests for Phase 7 point rebucketing helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sva.points.service import (
    PointBoundaryPatch,
    _build_replacement_points,
    _rebucket_event_rows,
    _rebucket_observation_rows,
)


def test_build_replacement_points_rejects_overlapping_ranges():
    with pytest.raises(ValueError, match="ordered and non-overlapping"):
        _build_replacement_points(
            "game_rebucket_001",
            [
                PointBoundaryPatch(start_video_ts_ms=0, end_video_ts_ms=10000),
                PointBoundaryPatch(start_video_ts_ms=10000, end_video_ts_ms=20000),
            ],
        )


def test_rebucket_helpers_update_events_and_observations_from_new_boundaries():
    points = _build_replacement_points(
        "game_rebucket_001",
        [
            PointBoundaryPatch(start_video_ts_ms=0, end_video_ts_ms=11000),
            PointBoundaryPatch(start_video_ts_ms=11001, end_video_ts_ms=22000),
        ],
    )
    event_rows = [
        SimpleNamespace(
            event_id="evt_001",
            video_ts_ms=12000,
            point_id="game_rebucket_001:pt_001",
            point_ordinal=1,
            in_point_ts_ms=12000,
        )
    ]
    observation_rows = [
        SimpleNamespace(
            observation_id="obs_001",
            observation_ts_ms=12500,
            point_id="game_rebucket_001:pt_001",
            point_ordinal=1,
        )
    ]

    events_rebucketed = _rebucket_event_rows(event_rows, points)
    observations_rebucketed = _rebucket_observation_rows(observation_rows, points)

    assert events_rebucketed == 1
    assert event_rows[0].point_id == "game_rebucket_001:pt_002"
    assert event_rows[0].point_ordinal == 2
    assert event_rows[0].in_point_ts_ms == 999
    assert observations_rebucketed == 1
    assert observation_rows[0].point_id == "game_rebucket_001:pt_002"
    assert observation_rows[0].point_ordinal == 2


def test_rebucket_helpers_reject_rows_outside_edited_boundaries():
    points = _build_replacement_points(
        "game_rebucket_001",
        [PointBoundaryPatch(start_video_ts_ms=0, end_video_ts_ms=9000)],
    )
    event_rows = [
        SimpleNamespace(
            event_id="evt_missing",
            video_ts_ms=12000,
            point_id="game_rebucket_001:pt_001",
            point_ordinal=1,
            in_point_ts_ms=12000,
        )
    ]

    with pytest.raises(ValueError, match="falls outside the edited point boundaries"):
        _rebucket_event_rows(event_rows, points)
