"""Builder daemon tick and CLI entry point."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

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
    """Placeholder repository implementation to be wired to real storage."""

    def select_due_jobs(self, now: datetime) -> Iterable[DueJob]:
        """Return no jobs in the stub implementation."""
        return ()

    def instantiate_job_tasks(self, job_id: str) -> int:
        """Return zero as no tasks are created."""
        return 0

    def set_job_running_if_new_tasks(self, job_id: str, created: int) -> None:
        """No-op for stub implementation."""
        return None

    def apply_retry_backoff(self, now: datetime) -> int:
        """Return zero as no retries are scheduled."""
        return 0

    def maybe_finish_job(self, job_id: str) -> bool:
        """Return ``False`` to indicate unfinished job."""
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
        Total number of actions performed.

        An action is one of:
            * a job had tasks created for it,
            * a job finished, or
            * a job retried via backoff.

    Side Effects:
        Emits a single ``logger.info("builder.tick", extra={...})`` entry summarizing
        the cycle.
    """
    repo = repo or DefaultRepo()
    now = now or datetime.now(UTC)

    due_jobs = list(repo.select_due_jobs(now))
    jobs_with_creates = 0
    finished_count = 0

    for due in due_jobs:
        created = repo.instantiate_job_tasks(due.job_id)
        if created > 0:
            repo.set_job_running_if_new_tasks(due.job_id, created)
            jobs_with_creates += 1
        if repo.maybe_finish_job(due.job_id):
            finished_count += 1

    retries = repo.apply_retry_backoff(now)
    actions = jobs_with_creates + retries + finished_count
    logger.info(
        "builder.tick",
        extra={
            "due_jobs": len(due_jobs),
            "jobs_with_creates": jobs_with_creates,
            "retries": retries,
            "finishes": finished_count,
            "actions": actions,
        },
    )
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
        try:
            tick(repo=repo)
        except Exception:  # noqa: BLE001
            logger.exception("tick failed")
        time.sleep(args.every)
