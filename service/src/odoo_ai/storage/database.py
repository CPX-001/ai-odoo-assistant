"""Engine and transactional session lifecycle for Assistant persistence."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from odoo_ai.storage.config import DatabaseSettings

type SessionFactory = sessionmaker[Session]


def create_database_engine(settings: DatabaseSettings) -> Engine:
    """Create an engine only from validated Assistant database settings."""

    return create_engine(settings.url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create explicit sessions with no implicit commit or expiration."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: SessionFactory) -> Iterator[Session]:
    """Commit a unit of work or roll it back if the operation fails."""

    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
