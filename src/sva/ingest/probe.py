"""PyAV-based video metadata probe.

Used by ingest to detect VFR streams that must be transcoded to CFR before perception.
Returns a Pydantic VideoMetadata consistent with the model style in sva.models.
"""

from __future__ import annotations

from pathlib import Path

import av
from pydantic import BaseModel, ConfigDict, Field


class VideoMetadata(BaseModel):
    """Probed metadata about a video file."""

    model_config = ConfigDict(extra="forbid")
    path: str
    duration_s: float = Field(ge=0)
    codec: str
    fps_reported: float = Field(ge=0)
    fps_average: float = Field(ge=0)
    container: str
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    is_variable_fps: bool


def probe_metadata(path: Path | str) -> VideoMetadata:
    """Probe a video file using PyAV.

    Raises:
        FileNotFoundError: path does not exist
        ValueError: file cannot be opened as a video container
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Video not found: {p}")

    try:
        container = av.open(str(p))
    except av.FFmpegError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unable to open {p}: {exc}") from exc

    try:
        video_streams = [s for s in container.streams if s.type == "video"]
        if not video_streams:
            raise ValueError(f"No video stream in {p}")
        stream = video_streams[0]

        codec_name = stream.codec_context.name if stream.codec_context else "unknown"
        width = stream.codec_context.width if stream.codec_context else 0
        height = stream.codec_context.height if stream.codec_context else 0
        duration_s = float(container.duration) / 1_000_000.0 if container.duration else 0.0
        container_format = container.format.name if container.format else "unknown"

        # Reported fps from stream metadata — `base_rate` is the stream's declared nominal
        # rate (e.g., 30 for a source that was ever 30fps), while `average_rate` is the
        # arithmetic mean frames/duration. For VFR streams these diverge.
        base_rate = float(stream.base_rate or 0.0)
        avg_rate = float(stream.average_rate or 0.0)
        fps_reported = base_rate if base_rate > 0 else avg_rate

        # Average fps computed from total frames / duration (ground truth).
        frame_count = stream.frames if stream.frames else 0
        if duration_s > 0 and frame_count > 0:
            fps_average = frame_count / duration_s
        else:
            fps_average = avg_rate

        # VFR heuristic: any of the following flags a non-CFR stream.
        #   1. Invalid time_base (the canonical 0/0 bug from PITFALLS §Pitfall 10).
        #   2. Declared base_rate differs from arithmetic average_rate by > 0.5 fps — i.e.
        #      the stream *claims* 30fps but only delivered an average of 20.89fps, which
        #      only happens when frame spacing varies (VFR) or frames were dropped.
        #   3. Declared base_rate differs from computed frame-count-based average by > 0.5.
        time_base = stream.time_base
        rate_mismatch = (
            base_rate > 0
            and avg_rate > 0
            and abs(base_rate - avg_rate) > 0.5
        )
        frame_count_mismatch = (
            base_rate > 0
            and fps_average > 0
            and abs(base_rate - fps_average) > 0.5
        )
        is_variable_fps = (
            time_base is None
            or time_base.denominator == 0
            or rate_mismatch
            or frame_count_mismatch
        )

        return VideoMetadata(
            path=str(p),
            duration_s=duration_s,
            codec=codec_name,
            fps_reported=fps_reported,
            fps_average=fps_average,
            container=container_format,
            width=width,
            height=height,
            is_variable_fps=is_variable_fps,
        )
    finally:
        container.close()
