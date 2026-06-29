from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from whatsapp_ai_agent.config import Settings, get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_engine(settings: Settings | None = None) -> Engine:
    """Return a lazily initialized SQLAlchemy engine.

    Passing explicit settings builds a fresh engine for tests or one-off scripts.
    The application default is created only when a DB dependency is actually used.
    """

    global _engine
    if settings is not None:
        return build_engine(settings)
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    global _session_factory
    if settings is not None:
        return sessionmaker(bind=get_engine(settings), autoflush=False, autocommit=False)
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _session_factory


def get_db_session() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session
