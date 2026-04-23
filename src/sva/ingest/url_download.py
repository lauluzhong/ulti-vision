"""yt-dlp-backed public URL download for approved Phase 2 sources."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from sva.ingest.sources import (
    PublicUrlAuthenticationRequiredError,
    RemoteUrlSource,
    SourcePolicyError,
    validate_remote_source,
)

DOWNLOAD_DIR = Path("data/downloads")


def _pick_downloaded_file(before: set[Path], after: set[Path]) -> Path:
    created = sorted(after - before, key=lambda path: path.stat().st_mtime, reverse=True)
    if not created:
        raise RuntimeError("yt-dlp completed without producing a local file.")
    return created[0]


def download_public_video(url: str, *, game_id: str) -> Path:
    """Download an approved public URL to a local working file."""
    source = validate_remote_source(RemoteUrlSource(url=url, ack_rights=True, caller_id="downloader"))
    binary = shutil.which("yt-dlp")
    if binary is None:
        raise RuntimeError("yt-dlp is not installed. Install project dependencies before URL ingest.")

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    before = set(DOWNLOAD_DIR.glob(f"{game_id}_*"))
    output_template = DOWNLOAD_DIR / f"{game_id}_%(id)s.%(ext)s"
    result = subprocess.run(
        [
            binary,
            "--no-progress",
            "--no-warnings",
            "--no-playlist",
            "-o",
            str(output_template),
            source.url,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        message = "\n".join(part for part in (result.stderr, result.stdout) if part).strip()
        lowered = message.lower()
        if any(token in lowered for token in ("sign in", "cookies", "private", "authentication")):
            raise PublicUrlAuthenticationRequiredError(
                "URL requires authentication; only public URLs supported in v1."
            )
        raise SourcePolicyError(f"yt-dlp failed for '{source.url}': {message or 'unknown error'}")

    after = set(DOWNLOAD_DIR.glob(f"{game_id}_*"))
    return _pick_downloaded_file(before, after)


__all__ = ["DOWNLOAD_DIR", "download_public_video"]
