"""Unit tests for window_offsets — deterministic; no I/O."""

from __future__ import annotations

import pytest

from sva.ingest.sampler import window_offsets


def test_empty_duration():
    assert window_offsets(0) == []


def test_exact_multiple_of_window():
    # 10s, window=2s -> 5 windows
    offsets = window_offsets(10.0, window_size_s=2.0)
    assert offsets == [(0, 2000), (2000, 4000), (4000, 6000), (6000, 8000), (8000, 10000)]


def test_ragged_last_window_truncated():
    offsets = window_offsets(5.5, window_size_s=2.0)
    assert offsets[-1] == (4000, 5500)
    assert offsets[0] == (0, 2000)


def test_raises_on_invalid_window_size():
    with pytest.raises(ValueError):
        window_offsets(10.0, window_size_s=0)
