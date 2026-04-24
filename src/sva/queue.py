"""Thin queue transport wrapper for Phase 6 background jobs."""

from __future__ import annotations

from functools import lru_cache

from sva.config import settings
from sva.jobs_service import process_job

try:
    import dramatiq
    from dramatiq.brokers.redis import RedisBroker
except ModuleNotFoundError:  # pragma: no cover - depends on installed extras
    dramatiq = None  # type: ignore[assignment]
    RedisBroker = None  # type: ignore[assignment]


@lru_cache(maxsize=1)
def get_broker():
    """Return the configured Dramatiq broker."""
    if dramatiq is None or RedisBroker is None:
        raise RuntimeError("dramatiq + redis are not installed for background job execution")
    broker = RedisBroker(url=settings.redis_url)
    dramatiq.set_broker(broker)
    return broker


if dramatiq is not None:

    @dramatiq.actor(actor_name="process-job")
    def process_job_actor(job_id: str) -> None:
        process_job(job_id)

else:

    def process_job_actor(job_id: str) -> None:
        raise RuntimeError("dramatiq + redis are not installed for background job execution")


def enqueue_job(job_id: str) -> None:
    """Enqueue one durable background job by id."""
    if dramatiq is None:
        raise RuntimeError("dramatiq + redis are not installed for background job execution")
    get_broker()
    process_job_actor.send(job_id)


__all__ = ["enqueue_job", "get_broker", "process_job_actor"]
