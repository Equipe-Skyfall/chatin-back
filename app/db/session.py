from collections.abc import Generator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Singleton, built lazily - importing this module (as every repository
    does, for the `DbSession` alias) must not require DB settings to be valid;
    only actually opening a session should."""
    return create_engine(get_settings().SUPABASE_DB_URL, pool_pre_ping=True)


@lru_cache
def _get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = _get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def nova_sessao() -> Session:
    """A fresh, request-independent `Session` - for code that runs outside
    the request/response cycle (`BackgroundTasks`), where the request-scoped
    session from `get_db` is already closed by the time it would run. Caller
    owns closing it (see `app/services/trilha_pessoal_service.py`)."""
    return _get_session_factory()()


# Defined next to get_db so every repository's own provider function (and
# deps.py) can depend on a plain `Session` without repeating `Depends(get_db)`.
DbSession = Annotated[Session, Depends(get_db)]
