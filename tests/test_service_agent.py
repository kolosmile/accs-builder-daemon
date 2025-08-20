"""Tests for the service agent MVP."""

from __future__ import annotations

import sys
from datetime import UTC, datetime  # noqa: F401

import pytest

from accs_app.agents import service
from accs_app.agents.service import Task, _run_once


class FakeRepo:
    """In-memory repository capturing calls for assertions."""

    def __init__(self) -> None:
        self.tasks = [
            Task(id="t1", job_id="ja", task_key="k1", service="render"),
            Task(id="t2", job_id="jb", task_key="k1", service="render"),
        ]
        self.events: list[tuple[str, str]] = []
        self.done: list[tuple[str, dict | None]] = []
        self.errors: list[tuple[str, str]] = []

    def select_runnable(self, service: str, limit: int, now: datetime) -> list[Task]:
        """Return the predefined tasks."""
        return list(self.tasks)

    def claim_tasks(self, task_ids: list[str], node: str, now: datetime) -> list[str]:
        """Simulate claiming only the first task ID."""
        return [task_ids[0]]

    def mark_task_running(self, task_id: str, now: datetime) -> None:
        """Record that ``task_id`` entered running state."""
        self.events.append((task_id, "running"))

    def append_event(
        self,
        task_id: str,
        level: str,
        type: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        """Record an event for ``task_id``."""
        self.events.append((task_id, type))

    def mark_task_done(self, task_id: str, results: dict | None, now: datetime) -> None:
        """Store completion results for ``task_id``."""
        self.done.append((task_id, results))

    def mark_task_error(
        self,
        task_id: str,
        code: str,
        message: str,
        now: datetime,
        data: dict | None = None,
    ) -> None:
        """Store error information for ``task_id``."""
        self.errors.append((task_id, message))


def test_run_once_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    """_run_once processes a single claimed task and records events."""
    repo = FakeRepo()
    monkeypatch.setattr(service, "execute_task", lambda t: {"ok": True})

    _run_once("render", "node-1", 1, None, repo=repo)

    assert repo.done == [("t1", {"ok": True})]
    types = [t for _, t in repo.events]
    assert "task.start" in types and "task.done" in types


def test_run_once_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Task execution errors are recorded via mark_task_error and events."""
    repo = FakeRepo()

    def boom(_t: Task) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "execute_task", boom)

    _run_once("render", "node-1", 1, None, repo=repo)

    assert repo.errors and repo.errors[0][0] == "t1"
    types = [t for _, t in repo.events]
    assert "task.error" in types


def test_ordered_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tasks are processed in the order they are claimed."""
    repo = FakeRepo()
    repo.tasks = [
        Task(id="jobA_task1", job_id="jobA", task_key="k1", service="render"),
        Task(id="jobB_task1", job_id="jobB", task_key="k1", service="render"),
    ]
    monkeypatch.setattr(service, "execute_task", lambda t: {"ok": True})

    _run_once("render", "node-1", 1, None, repo=repo)

    assert repo.done[0][0] == "jobA_task1"


def test_cli_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI with --once invokes _run_once."""
    called: dict[str, tuple[str, ...]] = {}

    def fail(*_a: object, **_k: object) -> None:
        raise RuntimeError("run_agent called")

    monkeypatch.setattr(service, "run_agent", fail)

    def fake_run_once(
        service_name: str,
        node: str,
        capacity: int,
        dsn: str | None,
        *,
        repo: object | None = None,
    ) -> None:
        called["args"] = (service_name, node, str(capacity), dsn or "")

    monkeypatch.setattr(service, "_run_once", fake_run_once)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "accs-agent",
            "--service",
            "render",
            "--node",
            "n1",
            "--once",
            "--dsn",
            "sqlite://",
        ],
    )

    service.main()

    assert called["args"][0] == "render" and called["args"][1] == "n1"
