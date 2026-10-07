from collections.abc import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from app.core.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session() -> Iterator[Session]:
    """One session per request. Mutating routes commit explicitly; anything
    left uncommitted (including after an exception) is rolled back on close."""
    with Session(get_engine()) as session:
        yield session
