"""Window offset calculator and deterministic window identity helpers."""

from __future__ import annotations


def validate_sampling_fps(fps: int) -> int:
    """Accept only the v1 perception sampling envelope."""
    if fps < 1 or fps > 3:
        raise ValueError("fps must be within the v1 envelope: 1 <= fps <= 3")
    return fps


def window_offsets(
    duration_s: float,
    fps: int = 1,
    window_size_s: float = 2.0,
) -> list[tuple[int, int]]:
    """Return a list of (start_ms, end_ms) pairs covering [0, duration_s).

    Args:
        duration_s: Total video duration in seconds. Must be >= 0.
        fps: Sampling rate in the Phase 3 v1 envelope (1-3 fps).
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
    fps = validate_sampling_fps(fps)

    duration_ms = int(duration_s * 1000)
    window_ms = int(window_size_s * 1000)
    step_ms = int(1000 / fps)
    offsets: list[tuple[int, int]] = []
    start = 0
    while start < duration_ms:
        end = min(start + window_ms, duration_ms)
        offsets.append((start, end))
        start += step_ms
    return offsets


def make_window_id(
    *,
    video_id: str,
    start_ms: int,
    end_ms: int,
    fps: int,
) -> str:
    """Return the stable cache-facing identity for one sampled window."""
    fps = validate_sampling_fps(fps)
    return f"win_{video_id}_{fps}fps_{start_ms}_{end_ms}"


__all__ = ["make_window_id", "validate_sampling_fps", "window_offsets"]
