"""Minimal service agent executing claimed tasks."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from accs_infra.db.repo_base import DBRepoBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Task:
    """Description of a task to be executed by a service."""

    id: str
    job_id: str
    task_key: str
    service: str
    params: dict | None = None


class Repo(Protocol):
    """Repository facade used by :func:`run_agent` for persistence."""

    def select_runnable(
        self, service: str, limit: int, now: datetime
    ) -> Iterable[Task]:
        """Return runnable tasks for ``service`` ordered by job sequence."""

    def claim_tasks(self, task_ids: list[str], node: str, now: datetime) -> list[str]:
        """Attempt to claim ``task_ids`` for ``node`` and return claimed IDs."""

    def mark_task_running(self, task_id: str, now: datetime) -> None:
        """Mark a task as running."""

    def append_event(
        self,
        task_id: str,
        level: str,
        type: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        """Append an event entry for ``task_id``."""

    def mark_task_done(self, task_id: str, results: dict | None, now: datetime) -> None:
        """Mark ``task_id`` as successfully completed."""

    def mark_task_error(
        self,
        task_id: str,
        code: str,
        message: str,
        now: datetime,
        data: dict | None = None,
    ) -> None:
        """Mark ``task_id`` failed with ``code`` and ``message``."""


class DefaultRepo(DBRepoBase):
    """Repository implementation resolving ACCScore helpers dynamically."""

    def select_runnable(
        self, service: str, limit: int, now: datetime
    ) -> Iterable[Task]:
        """Return runnable tasks for ``service``."""
        logger.debug("select_runnable service=%s limit=%s now=%s", service, limit, now)
        rows: Iterable[Any] | None = None
        for path in (
            "accscore.db.tasks.select_runnable",
            "accscore.db.select_runnable",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                rows = self.with_conn(func, service, limit, now)
            except TypeError:
                return []
            break
        else:
            return []
        tasks: list[Task] = []
        for row in rows or []:
            if isinstance(row, Task):
                tasks.append(row)
                continue
            if isinstance(row, dict):
                tasks.append(
                    Task(
                        id=str(row.get("id")),
                        job_id=str(row.get("job_id")),
                        task_key=str(row.get("task_key")),
                        service=str(row.get("service", service)),
                        params=row.get("params"),
                    )
                )
        return tasks

    def claim_tasks(self, task_ids: list[str], node: str, now: datetime) -> list[str]:
        """Claim ``task_ids`` for ``node`` and return the claimed IDs."""
        logger.debug("claim_tasks ids=%s node=%s now=%s", task_ids, node, now)
        for path in (
            "accscore.db.tasks.claim_tasks",
            "accscore.db.claim_tasks",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                result = self.with_conn(func, task_ids, node, now)
            except TypeError:
                return []
            if result is None:
                return []
            return [str(r) for r in result]
        return []

    def mark_task_running(self, task_id: str, now: datetime) -> None:
        """Mark ``task_id`` as running."""
        for path in (
            "accscore.db.tasks.mark_task_running",
            "accscore.db.mark_task_running",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                self.with_conn(func, task_id, now)
            except TypeError:
                pass
            return

    def append_event(
        self,
        task_id: str,
        level: str,
        type: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        """Append an event for ``task_id``."""
        for path in (
            "accscore.db.events.append_event",
            "accscore.db.append_event",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                self.with_conn(func, task_id, level, type, message, data)
            except TypeError:
                pass
            return

    def mark_task_done(self, task_id: str, results: dict | None, now: datetime) -> None:
        """Mark ``task_id`` as completed."""
        for path in (
            "accscore.db.tasks.mark_task_done",
            "accscore.db.mark_task_done",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                self.with_conn(func, task_id, results, now)
            except TypeError:
                pass
            return

    def mark_task_error(
        self,
        task_id: str,
        code: str,
        message: str,
        now: datetime,
        data: dict | None = None,
    ) -> None:
        """Record an error for ``task_id``."""
        for path in (
            "accscore.db.tasks.mark_task_error",
            "accscore.db.mark_task_error",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                self.with_conn(func, task_id, code, message, now, data)
            except TypeError:
                pass
            return


def execute_task(task: Task) -> dict | None:
    """Execute ``task`` and return result.

    The MVP implementation merely logs the task and returns ``{"ok": True}``.
    """
    logger.info("execute_task task_id=%s", task.id)
    return {"ok": True}


def _run_once(
    service: str,
    node: str,
    capacity: int,
    dsn: str | None,
    *,
    repo: Repo | None = None,
) -> None:
    """Run a single iteration of the service agent."""
    repo = repo or DefaultRepo(dsn=dsn)
    now = datetime.now(UTC)
    tasks = list(repo.select_runnable(service, capacity, now))
    if not tasks:
        return None
    claimed = repo.claim_tasks([t.id for t in tasks], node, now)
    for task in tasks:
        if task.id not in claimed:
            continue
        repo.mark_task_running(task.id, now)
        repo.append_event(
            task.id, "info", "task.start", f"{service} start", {"node": node}
        )
        try:
            result = execute_task(task)
            repo.mark_task_done(task.id, result, datetime.now(UTC))
            repo.append_event(task.id, "info", "task.done", f"{service} done")
        except Exception as exc:  # pragma: no cover - defensive
            repo.mark_task_error(task.id, "runtime_error", str(exc), datetime.now(UTC))
            repo.append_event(task.id, "error", "task.error", str(exc))
    return None


def run_agent(
    service: str,
    node: str,
    *,
    capacity: int = 1,
    every: float = 1.0,
    dsn: str | None = None,
) -> None:
    """Continuously run the service agent loop."""
    repo = DefaultRepo(dsn=dsn)
    interval = max(0.05, every)
    while True:
        now = datetime.now(UTC)
        try:
            tasks = list(repo.select_runnable(service, capacity, now))
            if not tasks:
                time.sleep(interval)
                continue
            claimed_ids = repo.claim_tasks([t.id for t in tasks], node, now)
            for t in tasks:
                if t.id not in claimed_ids:
                    continue
                repo.mark_task_running(t.id, now)
                repo.append_event(
                    t.id, "info", "task.start", f"{service} start", {"node": node}
                )
                try:
                    result = execute_task(t)
                    repo.mark_task_done(t.id, result, datetime.now(UTC))
                    repo.append_event(t.id, "info", "task.done", f"{service} done")
                except Exception as exc:  # pragma: no cover - defensive
                    repo.mark_task_error(
                        t.id, "runtime_error", str(exc), datetime.now(UTC)
                    )
                    repo.append_event(t.id, "error", "task.error", str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("service.loop.failed: %s", exc)
            time.sleep(interval)


def main() -> None:
    """Command line interface for the service agent."""
    parser = argparse.ArgumentParser("accs-agent")
    parser.add_argument("--service", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--capacity", type=int, default=1)
    parser.add_argument("--every", type=float, default=1.0)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if args.once:
        _run_once(args.service, args.node, args.capacity, args.dsn)
    else:
        run_agent(
            args.service,
            args.node,
            capacity=args.capacity,
            every=args.every,
            dsn=args.dsn,
        )
