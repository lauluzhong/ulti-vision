"""Tests for sva.ingest.probe — requires ffmpeg on PATH for fixture generation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path("tests/fixtures")
CFR_BASELINE = FIXTURES / "cfr_baseline.mp4"
VFR_SYNTHETIC = FIXTURES / "vfr_synthetic.mp4"

def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None

@pytest.fixture(scope="module", autouse=True)
def _ensure_fixtures():
    if not _ffmpeg_available():
        pytest.skip("ffmpeg not found on PATH; install via brew/apt")
    FIXTURES.mkdir(parents=True, exist_ok=True)

    if not CFR_BASELINE.exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "testsrc=duration=30:size=320x240:rate=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(CFR_BASELINE),
            ],
            check=True,
            capture_output=True,
        )

    if not VFR_SYNTHETIC.exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "testsrc=duration=30:size=320x240:rate=30",
                "-vf",
                "settb=AVTB,setpts=if(lt(N\\,30)\\,N/3\\,if(lt(N\\,60)\\,N/10\\,N/30))/TB",
                "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(VFR_SYNTHETIC),
            ],
            check=True,
            capture_output=True,
        )

def test_probe_cfr_baseline():
    from sva.ingest.probe import probe_metadata

    meta = probe_metadata(CFR_BASELINE)
    assert meta.codec in {"h264", "libx264"}
    assert 29.0 <= meta.duration_s <= 31.0
    assert meta.is_variable_fps is False
    assert meta.width == 320 and meta.height == 240

def test_probe_vfr_synthetic_detects_variable():
    from sva.ingest.probe import probe_metadata

    meta = probe_metadata(VFR_SYNTHETIC)
    assert meta.is_variable_fps is True, (
        f"Expected VFR detection; reported={meta.fps_reported} average={meta.fps_average}"
    )

def test_probe_missing_file_raises():
    from sva.ingest.probe import probe_metadata

    with pytest.raises(FileNotFoundError):
        probe_metadata(Path("/nonexistent/video.mp4"))
