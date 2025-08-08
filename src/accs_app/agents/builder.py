"""Builder daemon tick and CLI entry point."""

from __future__ import annotations

import argparse
import importlib
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DueJob:
    """Identifier for a job that should be processed."""

    job_id: str


class Repo(Protocol):
    """Repository facade used by :func:`tick` for persistence."""

    def select_due_jobs(self, now: datetime) -> Iterable[DueJob]:
        """Return jobs that are scheduled to run by ``now``."""

    def instantiate_job_tasks(self, job_id: str) -> int:
        """Instantiate tasks for the given job and return count of new tasks."""

    def set_job_running_if_new_tasks(self, job_id: str, created: int) -> None:
        """Mark the job running when new tasks were created."""

    def apply_retry_backoff(self, now: datetime) -> int:
        """Perform retry/backoff housekeeping and return number of jobs retried."""

    def maybe_finish_job(self, job_id: str) -> bool:
        """Attempt to finish job and return ``True`` if finished."""


class DefaultRepo:
    """Repository implementation delegating to the ACCScore package."""

    def _resolve(self, path: str) -> Callable[..., Any]:
        """Resolve a dotted path to a callable.

        Args:
            path: Dotted import path (e.g. ``"pkg.mod.func"``).

        Returns:
            Imported attribute referenced by ``path``.

        Raises:
            KeyError: If the module or attribute cannot be imported.
        """
        module_name, attr = path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_name)
            return getattr(module, attr)
        except (ModuleNotFoundError, AttributeError) as exc:  # pragma: no cover
            raise KeyError(path) from exc

    def select_due_jobs(self, now: datetime) -> Iterable[DueJob]:
        """Fetch due jobs from ACCScore and adapt rows to :class:`DueJob`."""
        rows = self._resolve("accscore.db.jobs.select_due_jobs")(now)
        return [DueJob(job_id=row["id"]) for row in rows]

    def instantiate_job_tasks(self, job_id: str) -> int:
        """Instantiate tasks for ``job_id`` via ACCScore."""
        func = self._resolve("accscore.db.jobs.instantiate_job_tasks")
        return int(func(job_id))

    def set_job_running_if_new_tasks(self, job_id: str, created: int) -> None:
        """Delegate to ACCScore when ``created`` is positive."""
        if created <= 0:
            return None
        func = self._resolve("accscore.db.jobs.set_job_running_if_new_tasks")
        func(job_id, created)
        return None

    def apply_retry_backoff(self, now: datetime) -> int:
        """Invoke ACCScore backoff housekeeping if available."""
        try:
            func = self._resolve("accscore.db.jobs.apply_retry_backoff")
        except KeyError:
            logger.info("apply_retry_backoff not available")
            return 0
        return int(func(now))

    def maybe_finish_job(self, job_id: str) -> bool:
        """Attempt job completion via ACCScore."""
        func = self._resolve("accscore.db.jobs.maybe_finish_job")
        return bool(func(job_id))


def tick(repo: Repo | None = None, *, now: datetime | None = None) -> int:
    """Execute one builder cycle.

    The cycle performs the following actions:
      * select due jobs (queued & scheduled_at <= now)
      * instantiate tasks from workflow
      * set job running if tasks were created
      * apply retry/backoff pass
      * attempt to finish jobs

    Args:
        repo: Repository implementation to use. Defaults to :class:`DefaultRepo`.
        now: Current time. Defaults to ``datetime.now(UTC)``.

    Returns:
        Number of actions performed (jobs with created tasks + retries + finishes).
    """
    repo = repo or DefaultRepo()
    now = now or datetime.now(UTC)

    actions = 0
    for due in repo.select_due_jobs(now):
        created = repo.instantiate_job_tasks(due.job_id)
        if created > 0:
            repo.set_job_running_if_new_tasks(due.job_id, created)
            actions += 1
        if repo.maybe_finish_job(due.job_id):
            actions += 1
    actions += repo.apply_retry_backoff(now)
    logger.info("tick actions=%s", actions)
    return actions


def main() -> None:
    """Command line interface for the builder daemon."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--every", type=float, default=2.0, help="Seconds between ticks"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run a single tick and exit"
    )
    args = parser.parse_args()

    repo: Repo = DefaultRepo()
    if args.once:
        tick(repo=repo)
        return

    while True:
        tick(repo=repo)
        time.sleep(args.every)
