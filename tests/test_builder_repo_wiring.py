"""Test ``DefaultRepo`` calls ACCScore paths with fallbacks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from accs_app.agents import builder
from accs_app.agents.builder import DefaultRepo


def _patch_resolve(
    monkeypatch: pytest.MonkeyPatch, mapping: dict[str, Callable[..., Any] | Exception]
) -> None:
    """Patch ``builder._resolve`` to return stubs or raise per ``mapping``."""

    def fake_resolve(path: str) -> Any:
        result = mapping.get(path)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise RuntimeError(path)
        return result

    monkeypatch.setattr(builder, "_resolve", fake_resolve)
    monkeypatch.setattr(builder.DefaultRepo, "_resolve", staticmethod(fake_resolve))


def test_select_due_jobs_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Primary path returns job identifiers from heterogeneous rows."""
    now = datetime(2024, 1, 1, tzinfo=UTC)

    def stub(now_param: datetime) -> list[Any]:  # noqa: ARG001
        return [{"id": "j1"}, {"job_id": "j2"}, "j3"]

    _patch_resolve(monkeypatch, {"accscore.db.jobs.select_due_jobs": stub})
    repo = DefaultRepo()
    ids = [d.job_id for d in repo.select_due_jobs(now)]
    assert ids == ["j1", "j2", "j3"]


def test_select_due_jobs_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back to alternate path when primary resolution fails."""
    now = datetime(2024, 1, 1, tzinfo=UTC)

    def stub(now_param: datetime) -> list[Any]:  # noqa: ARG001
        return [{"id": "j1"}, {"job_id": "j2"}, "j3"]

    _patch_resolve(
        monkeypatch,
        {
            "accscore.db.jobs.select_due_jobs": RuntimeError(),
            "accscore.db.select_due_jobs": stub,
        },
    )
    repo = DefaultRepo()
    ids = [d.job_id for d in repo.select_due_jobs(now)]
    assert ids == ["j1", "j2", "j3"]


def test_instantiate_job_tasks_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """instantiate_job_tasks falls back to alternate path."""

    def stub(job_id: str) -> int:  # noqa: ARG001
        return 2

    _patch_resolve(
        monkeypatch,
        {
            "accscore.db.jobs.instantiate_job_tasks": RuntimeError(),
            "accscore.db.instantiate_tasks": stub,
        },
    )
    repo = DefaultRepo()
    assert repo.instantiate_job_tasks("job-1") == 2


def test_apply_retry_backoff_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Returns zero and logs when both helper paths are missing."""
    _patch_resolve(
        monkeypatch,
        {
            "accscore.db.tasks.apply_retry_backoff": RuntimeError(),
            "accscore.db.jobs.apply_retry_backoff": RuntimeError(),
        },
    )
    repo = DefaultRepo()
    caplog.set_level(logging.INFO)
    now = datetime(2024, 1, 1, tzinfo=UTC)
    assert repo.apply_retry_backoff(now) == 0
    assert any("apply_retry_backoff.missing" in rec.message for rec in caplog.records)


def test_maybe_finish_job_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """maybe_finish_job uses secondary path when primary fails."""

    def stub(job_id: str) -> bool:  # noqa: ARG001
        return True

    _patch_resolve(
        monkeypatch,
        {
            "accscore.db.jobs.maybe_finish_job": RuntimeError(),
            "accscore.db.maybe_finish_job": stub,
        },
    )
    repo = DefaultRepo()
    assert repo.maybe_finish_job("job-1") is True
