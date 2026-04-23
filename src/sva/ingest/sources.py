"""Source input models and rights-safe public URL policy."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from sva.db import Base, session_scope

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}
UFA_HOSTS = {
    "watchufa.com",
    "www.watchufa.com",
    "watchufa.tv",
    "www.watchufa.tv",
}
ALLOWED_PUBLIC_VIDEO_HOSTS = tuple(sorted(YOUTUBE_HOSTS | UFA_HOSTS))
SUPPORTED_LOCAL_VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm")


class SourcePolicyError(ValueError):
    """Base class for rejected source inputs."""


class UnsupportedSourceError(SourcePolicyError):
    """Raised when a public URL is outside the Phase 2 allowlist."""


class RightsAckRequiredError(SourcePolicyError):
    """Raised when remote ingest is requested without an explicit rights ack."""


class PublicUrlAuthenticationRequiredError(SourcePolicyError):
    """Raised when a URL cannot be fetched anonymously in v1."""


@dataclass(frozen=True)
class LocalFileSource:
    path: str | Path


@dataclass(frozen=True)
class RemoteUrlSource:
    url: str
    ack_rights: bool
    caller_id: str


class RightsAckRow(Base):
    """Immutable record of URL rights acknowledgment before fetch."""

    __tablename__ = "rights_acks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    game_id = Column(Text, nullable=False, index=True)
    source_url = Column(Text, nullable=False)
    source_host = Column(Text, nullable=False, index=True)
    caller_id = Column(Text, nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


@lru_cache(maxsize=32)
def _normalized_host(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsupportedSourceError("Only http/https public video URLs are supported in v1.")
    host = parsed.netloc.lower().strip()
    if not host:
        raise UnsupportedSourceError("Public video URL is missing a hostname.")
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def validate_remote_source(source: RemoteUrlSource) -> RemoteUrlSource:
    """Enforce the Phase 2 public URL policy before any fetch begins."""
    if not source.ack_rights:
        raise RightsAckRequiredError(
            "URL ingest requires --ack-rights / rights_ack=true before yt-dlp is invoked."
        )
    if not source.caller_id.strip():
        raise SourcePolicyError("caller_id is required for URL ingest logging.")
    host = _normalized_host(source.url)
    if host not in ALLOWED_PUBLIC_VIDEO_HOSTS:
        raise UnsupportedSourceError(
            f"Unsupported public video host '{host}'. Only YouTube and UFA pages are supported in v1."
        )
    return source


def validate_local_source(source: LocalFileSource) -> LocalFileSource:
    """Enforce the Phase 2 local file extension policy."""
    suffix = str(source.path).lower()
    if not suffix.endswith(SUPPORTED_LOCAL_VIDEO_EXTENSIONS):
        raise UnsupportedSourceError(
            "Unsupported local video file extension. Supported types: mp4, mov, m4v, webm."
        )
    return source


def log_rights_ack(*, game_id: str, source_url: str, caller_id: str) -> None:
    """Persist the per-call URL rights acknowledgment."""
    host = _normalized_host(source_url)
    with session_scope() as session:
        session.add(
            RightsAckRow(
                game_id=game_id,
                source_url=source_url,
                source_host=host,
                caller_id=caller_id,
            )
        )


__all__ = [
    "ALLOWED_PUBLIC_VIDEO_HOSTS",
    "LocalFileSource",
    "PublicUrlAuthenticationRequiredError",
    "RemoteUrlSource",
    "RightsAckRequiredError",
    "RightsAckRow",
    "SourcePolicyError",
    "UnsupportedSourceError",
    "log_rights_ack",
    "validate_local_source",
    "validate_remote_source",
    "SUPPORTED_LOCAL_VIDEO_EXTENSIONS",
]
