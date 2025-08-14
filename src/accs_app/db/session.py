"""SQLAlchemy session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine


def get_engine(dsn: str) -> Engine:
    """Create an :class:`~sqlalchemy.engine.Engine` for ``dsn``.

    Args:
        dsn: Database connection string.

    Returns:
        New SQLAlchemy engine configured for future mode.
    """
    return create_engine(dsn, future=True)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Connection]:
    """Provide a transactional scope around a series of operations.

    Args:
        engine: SQLAlchemy engine to create a session from.

    Yields:
        An active connection within a transaction.
    """
    with engine.begin() as conn:
        yield conn
