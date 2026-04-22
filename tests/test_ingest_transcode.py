"""Tests for sva.ingest.transcode — VFR → CFR correctness."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path("tests/fixtures")
VFR_SYNTHETIC = FIXTURES / "vfr_synthetic.mp4"


@pytest.fixture(scope="module", autouse=True)
def _ensure_vfr_fixture():
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not found on PATH")
    FIXTURES.mkdir(parents=True, exist_ok=True)
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


def test_transcode_produces_cfr(tmp_path):
    from sva.ingest.transcode import transcode_to_cfr
    from sva.ingest.probe import probe_metadata

    dst = tmp_path / "out.mp4"
    out_meta = transcode_to_cfr(VFR_SYNTHETIC, dst, fps=1)
    assert dst.exists()
    assert out_meta.is_variable_fps is False
    assert abs(out_meta.fps_average - 1.0) < 0.2, (
        f"Expected ~1fps CFR, got average={out_meta.fps_average}"
    )

    # Re-probe independently to confirm.
    reprobed = probe_metadata(dst)
    assert reprobed.codec in {"h264", "libx264"}
    assert reprobed.is_variable_fps is False


def test_transcode_missing_source_raises(tmp_path):
    from sva.ingest.transcode import transcode_to_cfr

    with pytest.raises(FileNotFoundError):
        transcode_to_cfr(Path("/nope.mp4"), tmp_path / "out.mp4")
