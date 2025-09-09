from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import get_settings


_engine: Optional[Engine] = None


def get_engine() -> Optional[Engine]:
    global _engine
    if _engine is not None:
        return _engine
    settings = get_settings()
    url = settings.effective_database_url
    if not url:
        return None
    _engine = create_engine(url, pool_pre_ping=True, future=True)
    return _engine


@contextmanager
def session_scope() -> Iterator[Engine]:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("Database is not configured (DATABASE_URL or SUPABASE_DB_URL missing)")
    with engine.begin() as conn:
        yield conn

