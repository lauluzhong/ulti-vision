"""Unit tests for sampler fps envelope and deterministic window identity."""

from __future__ import annotations

import pytest

from sva.ingest.sampler import make_window_id, window_offsets


def test_empty_duration():
    assert window_offsets(0) == []


def test_rejects_invalid_window_size():
    with pytest.raises(ValueError):
        window_offsets(10.0, window_size_s=0)


@pytest.mark.parametrize(
    ("fps", "expected"),
    [
        (1, [(0, 2000), (1000, 3000), (2000, 4000), (3000, 4000)]),
        (2, [(0, 2000), (500, 2500), (1000, 3000), (1500, 3500), (2000, 4000), (2500, 4000), (3000, 4000), (3500, 4000)]),
        (3, [(0, 2000), (333, 2333), (666, 2666), (999, 2999), (1332, 3332), (1665, 3665), (1998, 3998), (2331, 4000), (2664, 4000), (2997, 4000), (3330, 4000), (3663, 4000), (3996, 4000)]),
    ],
)
def test_window_offsets_respect_sampling_fps(fps, expected):
    assert window_offsets(4.0, fps=fps, window_size_s=2.0) == expected


def test_window_offsets_reject_above_v1_envelope():
    with pytest.raises(ValueError, match="1 <= fps <= 3"):
        window_offsets(4.0, fps=4)


def test_window_id_is_deterministic_and_fps_sensitive():
    first = make_window_id(video_id="vid_123", start_ms=1000, end_ms=3000, fps=1)
    second = make_window_id(video_id="vid_123", start_ms=1000, end_ms=3000, fps=1)
    different_fps = make_window_id(video_id="vid_123", start_ms=1000, end_ms=3000, fps=2)

    assert first == second
    assert different_fps != first
