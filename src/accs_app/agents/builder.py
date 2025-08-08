"""Builder daemon tick and CLI entry point."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


def _resolve(path: str) -> Callable[..., Any]:
    """Resolve dotted ``path`` to a callable.

    The referenced object is imported lazily and returned. A ``RuntimeError`` is
    raised when the module or attribute cannot be resolved.

    Args:
        path: Dotted import path to resolve.

    Returns:
        The resolved callable.

    Raises:
        RuntimeError: If the target cannot be imported or is missing.
    """
    module_path, _, attr = path.rpartition(".")
    if not module_path or not attr:
        raise RuntimeError(f"invalid import path: {path}")
    try:
        module = import_module(module_path)
    except ModuleNotFoundError as exc:  # pragma: no cover - importlib error
        raise RuntimeError(f"module not found: {module_path}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:  # pragma: no cover - attribute error
        raise RuntimeError(f"attribute not found: {path}") from exc


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
    """Repository implementation resolving helper functions dynamically."""

    def select_due_jobs(self, now: datetime) -> Iterable[DueJob]:
        """Return jobs scheduled to run by ``now``."""
        logger.debug("select_due_jobs now=%s", now)
        try:
            func = _resolve("accscore.db.jobs.select_due_jobs")
        except RuntimeError:
            return []
        try:
            rows = func(now)
        except TypeError:
            return []
        return [DueJob(job_id=str(row)) for row in rows]

    def instantiate_job_tasks(self, job_id: str) -> int:
        """Instantiate tasks for ``job_id`` and return count of created tasks."""
        logger.debug("instantiate_job_tasks job_id=%s", job_id)
        try:
            func = _resolve("accscore.db.jobs.instantiate_job_tasks")
        except RuntimeError:
            return 0
        try:
            created = func(job_id)
        except TypeError:
            return 0
        return int(created)

    def set_job_running_if_new_tasks(self, job_id: str, created: int) -> None:
        """Mark job running when ``created`` > 0."""
        logger.debug(
            "set_job_running_if_new_tasks job_id=%s created=%s", job_id, created
        )
        if created <= 0:
            return None
        try:
            func = _resolve("accscore.db.jobs.set_job_running_if_queued")
        except RuntimeError:
            return None
        try:
            func(job_id)
        except TypeError:
            return None
        return None

    def apply_retry_backoff(self, now: datetime) -> int:
        """Apply retry/backoff housekeeping."""
        logger.debug("apply_retry_backoff now=%s", now)
        try:
            func = _resolve("accscore.db.tasks.apply_retry_backoff")
        except RuntimeError:
            return 0
        try:
            return int(func(now))
        except TypeError:
            return 0

    def maybe_finish_job(self, job_id: str) -> bool:
        """Attempt to finish job ``job_id`` and return completion state."""
        logger.debug("maybe_finish_job job_id=%s", job_id)
        try:
            func = _resolve("accscore.db.jobs.maybe_finish_job")
        except RuntimeError:
            return False
        try:
            return bool(func(job_id))
        except TypeError:
            return False


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
