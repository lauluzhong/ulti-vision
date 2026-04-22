"""Window offset calculator. Phase 3 extends this with point-aware chunking."""

from __future__ import annotations


def window_offsets(
    duration_s: float,
    fps: int = 1,
    window_size_s: float = 2.0,
) -> list[tuple[int, int]]:
    """Return a list of (start_ms, end_ms) pairs covering [0, duration_s).

    Args:
        duration_s: Total video duration in seconds. Must be >= 0.
        fps: Sampling rate (default 1 fps per PERCEIVE-01). Currently unused in window
            calculation; reserved for Phase 3 adaptive sampling.
        window_size_s: Window duration in seconds (default 2.0 — matches
            Observation.video_ts_end_ms - video_ts_start_ms in the example in
            ARCHITECTURE.md).

    Returns:
        List of (start_ms, end_ms) pairs. Last window is clipped to ``duration_s``.
    """
    if duration_s <= 0:
        return []
    if window_size_s <= 0:
        raise ValueError("window_size_s must be positive")
    _ = fps  # reserved for Phase 3

    duration_ms = int(duration_s * 1000)
    step_ms = int(window_size_s * 1000)
    offsets: list[tuple[int, int]] = []
    start = 0
    while start < duration_ms:
        end = min(start + step_ms, duration_ms)
        offsets.append((start, end))
        start = end
    return offsets
