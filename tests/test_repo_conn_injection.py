"""Tests for connection injection and session helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from accs_builder_daemon.repo.builder_repo import DefaultRepo
from accs_infra.db.session import get_engine, session_scope


def test_repo_conn_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    """DefaultRepo methods inject ``conn`` when required."""
    calls: dict[str, object] = {}

    def f(_now: datetime, *, conn: object) -> list[dict[str, str]]:
        calls["conn"] = conn
        return [{"id": "j1"}]

    def g(_job_id: str) -> int:
        calls["g"] = True
        return 1

    mapping = {
        "accscore.db.jobs.select_due_jobs": f,
        "accscore.db.jobs.instantiate_job_tasks": g,
    }

    def fake_resolve(path: str) -> object:
        return mapping[path]

    monkeypatch.setattr(DefaultRepo, "_resolve", staticmethod(fake_resolve))

    repo = DefaultRepo(dsn="sqlite://")
    now = datetime(2024, 1, 1, tzinfo=UTC)

    assert [d.job_id for d in repo.select_due_jobs(now)] == ["j1"]
    assert calls["conn"] is not None
    assert repo.instantiate_job_tasks("job") == 1
    assert calls["g"] is True


def test_session_scope_smoke() -> None:
    """session_scope opens a transaction and yields a connection."""
    engine = get_engine("sqlite://")
    with session_scope(engine) as conn:
        res = conn.exec_driver_sql("select 1")
        assert res.scalar() == 1
