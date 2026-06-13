"""SQLAlchemy engine/session wiring.

Works against Postgres (docker compose / Azure) and SQLite (tests). The engine
is created lazily and cached per process.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        # Allow the SQLite test DB to be shared across threads (FastAPI/worker).
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)


@lru_cache
def get_sessionmaker(database_url: str) -> sessionmaker:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False, future=True)


def create_all(database_url: str) -> None:
    """Create tables if they don't exist. Import models so they register."""
    from audit import models  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(get_engine(database_url))


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    """Transactional session context: commit on success, rollback on error."""
    session = get_sessionmaker(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
