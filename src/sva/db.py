"""SQLAlchemy engine + session factory for the sva package."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from sva.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM tables. Registered with Alembic target_metadata."""


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a process-wide singleton engine bound to settings.database_url."""
    return create_engine(settings.database_url, future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session scope: commit on clean exit, rollback on exception."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
