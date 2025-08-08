"""DefaultRepo wiring to ACCScore functions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from accs_app.agents.builder import DefaultRepo, DueJob


def test_select_due_jobs_wires_to_accscore(monkeypatch: pytest.MonkeyPatch) -> None:
    """select_due_jobs resolves to the ACCScore path."""
    repo = DefaultRepo()

    def fake_resolve(path: str) -> object:
        assert path == "accscore.db.jobs.select_due_jobs"

        def stub(now: datetime) -> list[dict[str, str]]:  # noqa: ARG001
            return [{"id": "job-1"}, {"id": "job-2"}]

        return stub

    monkeypatch.setattr(repo, "_resolve", fake_resolve)

    jobs = list(repo.select_due_jobs(datetime(2024, 1, 1, tzinfo=UTC)))
    assert jobs == [DueJob(job_id="job-1"), DueJob(job_id="job-2")]


def test_instantiate_job_tasks_wires_to_accscore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """instantiate_job_tasks delegates to ACCScore."""
    monkeypatch.setenv("ACC_MINIO_ENDPOINT", "x")
    monkeypatch.setenv("ACC_MINIO_ACCESS_KEY", "x")
    monkeypatch.setenv("ACC_MINIO_SECRET_KEY", "x")
    monkeypatch.setenv("ACC_DB_URL", "sqlite://")
    from accscore.db import jobs as jobs_mod  # type: ignore[import-not-found]

    def stub(job_id: str) -> int:
        assert job_id == "job-1"
        return 2

    monkeypatch.setattr(jobs_mod, "instantiate_job_tasks", stub)
    repo = DefaultRepo()
    assert repo.instantiate_job_tasks("job-1") == 2


def test_set_job_running_if_new_tasks_noop_when_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """set_job_running_if_new_tasks does nothing when no tasks created."""
    repo = DefaultRepo()
    calls = {"count": 0}

    def fake_resolve(path: str) -> object:  # noqa: ARG001
        calls["count"] += 1
        return lambda *args, **kwargs: None

    monkeypatch.setattr(repo, "_resolve", fake_resolve)
    repo.set_job_running_if_new_tasks("job-1", 0)
    assert calls["count"] == 0


def test_apply_retry_backoff_returns_zero_when_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """apply_retry_backoff yields zero and logs when function missing."""
    repo = DefaultRepo()

    def fake_resolve(path: str) -> object:  # noqa: ARG001
        raise KeyError

    monkeypatch.setattr(repo, "_resolve", fake_resolve)
    caplog.set_level(logging.INFO)
    assert repo.apply_retry_backoff(datetime(2024, 1, 1, tzinfo=UTC)) == 0
    assert any("apply_retry_backoff" in rec.message for rec in caplog.records)


def test_maybe_finish_job_wires(monkeypatch: pytest.MonkeyPatch) -> None:
    """maybe_finish_job delegates to ACCScore."""
    monkeypatch.setenv("ACC_MINIO_ENDPOINT", "x")
    monkeypatch.setenv("ACC_MINIO_ACCESS_KEY", "x")
    monkeypatch.setenv("ACC_MINIO_SECRET_KEY", "x")
    monkeypatch.setenv("ACC_DB_URL", "sqlite://")
    from accscore.db import jobs as jobs_mod

    def stub(job_id: str) -> bool:
        assert job_id == "job-1"
        return True

    monkeypatch.setattr(jobs_mod, "maybe_finish_job", stub, raising=False)
    repo = DefaultRepo()
    assert repo.maybe_finish_job("job-1") is True
