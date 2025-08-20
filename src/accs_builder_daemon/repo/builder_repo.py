"""Repository implementation for builder tick logic."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from accs_builder_daemon.domain.tick import DueJob
from accs_infra.db.repo_base import DBRepoBase, _resolve  # noqa: F401

logger = logging.getLogger(__name__)


class DefaultRepo(DBRepoBase):
    """Repository implementation resolving helper functions dynamically."""

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
                rows = self.with_conn(func, now)
            except TypeError:
                return []
            break
        else:
            return []
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
            except RuntimeError:
                continue
            try:
                return int(self.with_conn(func, job_id) or 0)
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
        for path in (
            "accscore.db.jobs.set_job_running_if_queued",
            "accscore.db.jobs.set_job_running_if_new_tasks",
        ):
            try:
                func = self._resolve(path)
            except RuntimeError:
                continue
            try:
                self.with_conn(func, job_id)
                return None
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
                return int(self.with_conn(func, now) or 0)
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
            except RuntimeError:
                continue
            try:
                return bool(self.with_conn(func, job_id))
            except TypeError:
                return False
        return False
