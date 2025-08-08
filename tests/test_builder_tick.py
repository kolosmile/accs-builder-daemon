"""Tests for the builder tick loop and CLI."""

from collections.abc import Iterable
from datetime import UTC, datetime

import pytest

from accs_app.agents.builder import DueJob, Repo, main, tick


class FakeRepo(Repo):
    """In-memory repo used to observe builder interactions."""

    def __init__(
        self,
        *,
        due_jobs: list[str] | None = None,
        instantiate: dict[str, int] | None = None,
        retry: int = 0,
        finish: bool = False,
    ) -> None:
        self.due_jobs = due_jobs or []
        self.instantiate = instantiate or {}
        self.retry = retry
        self.finish = finish
        self.instantiate_calls: list[str] = []
        self.set_running_calls: list[tuple[str, int]] = []
        self.retry_calls = 0
        self.maybe_finish_calls: list[str] = []

    def select_due_jobs(self, now: datetime) -> Iterable[DueJob]:
        """Return configured due jobs."""
        return [DueJob(job_id=j) for j in self.due_jobs]

    def instantiate_job_tasks(self, job_id: str) -> int:
        """Record call and return configured count."""
        self.instantiate_calls.append(job_id)
        return self.instantiate.get(job_id, 0)

    def set_job_running_if_new_tasks(self, job_id: str, created: int) -> None:
        """Record set-running calls."""
        self.set_running_calls.append((job_id, created))

    def apply_retry_backoff(self, now: datetime) -> int:
        """Record retry pass and return configured count."""
        self.retry_calls += 1
        return self.retry

    def maybe_finish_job(self, job_id: str) -> bool:
        """Record finish attempts and return configured result."""
        self.maybe_finish_calls.append(job_id)
        return self.finish


def test_instantiate_path() -> None:
    """Instantiate tasks and mark job running."""
    repo = FakeRepo(due_jobs=["job-1"], instantiate={"job-1": 2})
    actions = tick(repo=repo, now=datetime(2024, 1, 1, tzinfo=UTC))
    assert repo.set_running_calls == [("job-1", 2)]
    assert repo.maybe_finish_calls == ["job-1"]
    assert repo.retry_calls == 1
    assert actions == 1


def test_finish_counts_as_action() -> None:
    """Finishing a job increments the action count."""
    repo = FakeRepo(due_jobs=["job-1"], finish=True)
    actions = tick(repo=repo, now=datetime(2024, 1, 1, tzinfo=UTC))
    assert repo.set_running_calls == []
    assert repo.maybe_finish_calls == ["job-1"]
    assert repo.retry_calls == 1
    assert actions == 1


def test_no_due_jobs_only_retry() -> None:
    """Return retry count when no jobs are due."""
    repo = FakeRepo(retry=3)
    actions = tick(repo=repo, now=datetime(2024, 1, 1, tzinfo=UTC))
    assert repo.instantiate_calls == []
    assert repo.set_running_calls == []
    assert actions == 3


def test_cli_once_calls_tick_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--once`` runs exactly one tick."""
    ran = {"called": False}

    def fake_tick(  # noqa: ARG001
        repo: Repo | None = None, *, now: datetime | None = None
    ) -> int:
        ran["called"] = True
        return 0

    monkeypatch.setattr("accs_app.agents.builder.tick", fake_tick)
    monkeypatch.setattr("sys.argv", ["accs-builder", "--once"])
    main()
    assert ran["called"] is True


def test_cli_loop_catches_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Loop retries after exceptions and logs them."""
    from accs_app.agents import builder

    calls = {"tick": 0, "logged": 0}

    def fake_tick(  # noqa: ARG001
        repo: Repo | None = None, *, now: datetime | None = None
    ) -> int:
        calls["tick"] += 1
        if calls["tick"] == 1:
            raise RuntimeError("boom")
        if getattr(builder, "_stop", False):
            raise SystemExit
        builder._stop = True  # type: ignore[attr-defined]
        return 0

    def fake_sleep(_seconds: float) -> None:  # noqa: ARG001
        return None

    def fake_exception(*_args: object, **_kwargs: object) -> None:
        calls["logged"] += 1

    monkeypatch.setattr(builder, "tick", fake_tick)
    monkeypatch.setattr(builder.time, "sleep", fake_sleep)
    monkeypatch.setattr(builder.logger, "exception", fake_exception)
    monkeypatch.setattr(builder, "_stop", False, raising=False)
    monkeypatch.setattr("sys.argv", ["accs-builder", "--every", "0"])

    with pytest.raises(SystemExit):
        main()

    assert calls["logged"] >= 1
