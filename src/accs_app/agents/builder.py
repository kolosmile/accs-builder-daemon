"""Builder daemon tick and CLI entry point."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

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
        module = __import__(module_path, fromlist=[attr])
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(f"module not found: {module_path}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:  # pragma: no cover
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

    _resolve = staticmethod(_resolve)

    def select_due_jobs(self, now: datetime) -> Iterable[DueJob]:
        """Return jobs scheduled to run by ``now``."""
        logger.debug("select_due_jobs now=%s", now)
        rows: Iterable[Any] | None = None
        for path in (
            "accscore.db.jobs.select_due_jobs",
            "accscore.db.select_due_jobs",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                rows = func(now)
            except TypeError:
                return []
            break
        else:
            return []
        # Be robust to row shape: dict with id / job_id, or raw id
        due: list[DueJob] = []
        for row in rows or []:
            if isinstance(row, dict):
                job_id = row.get("id") or row.get("job_id") or str(row)
            else:
                job_id = str(row)
            due.append(DueJob(job_id=job_id))
        return due

    def instantiate_job_tasks(self, job_id: str) -> int:
        """Instantiate tasks for ``job_id`` and return count of created tasks."""
        logger.debug("instantiate_job_tasks job_id=%s", job_id)
        for path in (
            "accscore.db.jobs.instantiate_job_tasks",
            "accscore.db.instantiate_tasks",
        ):
            try:
                func = self._resolve(path)
                return int(func(job_id) or 0)
            except RuntimeError:
                continue
            except TypeError:
                return 0
        return 0

    def set_job_running_if_new_tasks(self, job_id: str, created: int) -> None:
        """Mark job running when ``created`` > 0."""
        logger.debug(
            "set_job_running_if_new_tasks job_id=%s created=%s", job_id, created
        )
        if created <= 0:
            return None
        # Prefer a targeted helper if available; otherwise no-op in MVP.
        for path in (
            "accscore.db.jobs.set_job_running_if_queued",
            "accscore.db.jobs.set_job_running_if_new_tasks",
        ):
            try:
                func = self._resolve(path)
                func(job_id)
                return None
            except RuntimeError:
                continue
            except TypeError:
                return None
        return None

    def apply_retry_backoff(self, now: datetime) -> int:
        """Apply retry/backoff housekeeping."""
        logger.debug("apply_retry_backoff now=%s", now)
        for path in (
            "accscore.db.tasks.apply_retry_backoff",
            "accscore.db.jobs.apply_retry_backoff",
        ):
            try:
                func = self._resolve(path)
            except Exception:
                logger.info("apply_retry_backoff.missing path=%s", path)
                continue
            try:
                return int(func(now) or 0)
            except TypeError:
                return 0
            except Exception:
                return 0
        return 0

    def maybe_finish_job(self, job_id: str) -> bool:
        """Attempt to finish job ``job_id`` and return completion state."""
        logger.debug("maybe_finish_job job_id=%s", job_id)
        for path in (
            "accscore.db.jobs.maybe_finish_job",
            "accscore.db.maybe_finish_job",
        ):
            try:
                func = self._resolve(path)
                return bool(func(job_id))
            except RuntimeError:
                continue
            except TypeError:
                return False
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
        Total number of actions performed (creates + retries + finishes).

    Side Effects:
        Emits a single ``logger.info("builder.tick", extra={...})`` summary.
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
    parser = argparse.ArgumentParser("accs-builder")
    parser.add_argument(
        "--every", type=float, default=2.0, help="Seconds between ticks"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run a single tick and exit"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    repo: Repo = DefaultRepo()

    if args.once:
        tick(repo=repo)
        return

    interval = max(0.05, float(args.every))
    while True:
        try:
            tick(repo=repo)
        except Exception as exc:  # pragma: no cover
            logger.exception("builder.tick.failed: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()
