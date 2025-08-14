"""Optional PostgreSQL integration smoke tests."""

from __future__ import annotations

import os

import pytest

from accs_app.db.session import get_engine, session_scope


def test_pg_connection() -> None:
    """Connect to PostgreSQL if ``ACC_DB_URL`` is provided."""
    dsn = os.environ.get("ACC_DB_URL")
    if not dsn:
        pytest.skip("no PG dsn")
    engine = get_engine(dsn)
    with session_scope(engine) as conn:
        assert conn.exec_driver_sql("select 1").scalar() == 1
