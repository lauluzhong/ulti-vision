"""Ingest package: source resolution, probe, transcode, sampler, ingest."""

from sva.ingest.ingest import (
    IngestResult,
    JobRow,
    ingest_clip,
    ingest_local_file,
    ingest_remote_url,
    ingest_source,
    load_ingest_result_for_job,
)
from sva.ingest.probe import VideoMetadata, probe_metadata
from sva.ingest.sampler import window_offsets
from sva.ingest.sources import (
    ALLOWED_PUBLIC_VIDEO_HOSTS,
    LocalFileSource,
    PublicUrlAuthenticationRequiredError,
    RemoteUrlSource,
    RightsAckRequiredError,
    SourcePolicyError,
    SUPPORTED_LOCAL_VIDEO_EXTENSIONS,
    UnsupportedSourceError,
    validate_local_source,
    validate_remote_source,
)
from sva.ingest.transcode import transcode_to_cfr
from sva.ingest.url_download import download_public_video

__all__ = [
    "ALLOWED_PUBLIC_VIDEO_HOSTS",
    "IngestResult",
    "JobRow",
    "LocalFileSource",
    "PublicUrlAuthenticationRequiredError",
    "RemoteUrlSource",
    "RightsAckRequiredError",
    "SourcePolicyError",
    "SUPPORTED_LOCAL_VIDEO_EXTENSIONS",
    "UnsupportedSourceError",
    "VideoMetadata",
    "download_public_video",
    "ingest_clip",
    "ingest_local_file",
    "ingest_remote_url",
    "ingest_source",
    "load_ingest_result_for_job",
    "probe_metadata",
    "transcode_to_cfr",
    "validate_local_source",
    "validate_remote_source",
    "window_offsets",
]
