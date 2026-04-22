"""VFR -> CFR transcoding via PyAV.

This is the Phase 1 non-negotiable (CONTEXT D-00, PITFALLS §Pitfall 10). Every downstream
phase assumes ingested video is constant-frame-rate. We use PyAV (not subprocess ffmpeg) so
frame-level control stays on one code path and no shell dependency sneaks in.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import av
import av.filter

from sva.ingest.probe import VideoMetadata, probe_metadata


def transcode_to_cfr(
    src: Path | str,
    dst: Path | str,
    fps: int = 1,
) -> VideoMetadata:
    """Transcode ``src`` to constant-frame-rate H.264 mp4 at ``fps`` frames per second.

    Equivalent to::

        ffmpeg -i src -vf fps={fps} -c:v libx264 -vsync cfr dst

    Returns probed metadata of the newly-written ``dst`` file.
    """
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.exists():
        raise FileNotFoundError(f"Source video not found: {src_path}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    in_container = av.open(str(src_path))
    out_container = av.open(str(dst_path), mode="w", format="mp4")

    try:
        in_video_streams = [s for s in in_container.streams if s.type == "video"]
        if not in_video_streams:
            raise ValueError(f"No video stream in {src_path}")
        in_stream = in_video_streams[0]

        width = in_stream.codec_context.width
        height = in_stream.codec_context.height
        pix_fmt = "yuv420p"

        out_stream = out_container.add_stream("libx264", rate=fps)
        out_stream.width = width
        out_stream.height = height
        out_stream.pix_fmt = pix_fmt
        out_stream.time_base = Fraction(1, fps)

        # Build a PyAV filter graph: fps=<fps> for constant-rate output.
        graph = av.filter.Graph()
        buffer = graph.add_buffer(template=in_stream)
        fps_filter = graph.add("fps", f"fps={fps}:round=up")
        buffer_sink = graph.add("buffersink")
        buffer.link_to(fps_filter)
        fps_filter.link_to(buffer_sink)
        graph.configure()

        frame_index = 0
        # Drain the filter graph whenever we've pushed a frame.
        def _drain_graph(is_flushed: bool) -> int:
            nonlocal frame_index
            drained = 0
            while True:
                try:
                    filtered = graph.pull()
                except (BlockingIOError, EOFError):
                    break
                except av.FFmpegError:
                    # FFmpegError with EAGAIN semantics in older PyAV paths.
                    break
                filtered.pts = frame_index
                filtered.time_base = Fraction(1, fps)
                for encoded in out_stream.encode(filtered):
                    out_container.mux(encoded)
                frame_index += 1
                drained += 1
            _ = is_flushed
            return drained

        for packet in in_container.demux(in_stream):
            for frame in packet.decode():
                graph.push(frame)
                _drain_graph(is_flushed=False)

        # Flush the filter graph with EOF, then drain the remaining filtered frames.
        graph.push(None)
        _drain_graph(is_flushed=True)

        # Flush the encoder.
        for encoded in out_stream.encode(None):
            out_container.mux(encoded)
    finally:
        out_container.close()
        in_container.close()

    return probe_metadata(dst_path)
