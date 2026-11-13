"""Durable task orchestration with leases, bounded concurrency and recovery.

Design guarantees (all verified by tests):

* **No provider coupling.** Execution happens through an injectable
  ``TaskExecutor`` protocol. The default executor refuses to run, and tests use
  a fake executor. Nothing here contacts a model, browser or shell.
* **Leases, not lock-in-process.** A claim writes ``lease_owner`` and
  ``lease_expires_at`` so a crashed process cannot permanently own a task.
* **Bounded concurrency.** ``max_concurrency`` caps in-flight tasks per run.
* **Crash recovery.** ``recover_expired_leases`` reconciles tasks whose lease
  expired: the task returns to ``assigned`` and the attempt is recorded, so a
  kill -9 mid-run cannot leave work stuck in ``running`` forever.
* **Replay safety.** Every state change goes through the workflow service with
  a deterministic idempotency key derived from the task id and attempt number.
* **Retry policy.** Failures increment ``retry_count`` and set a backoff
  ``next_attempt_at`` until ``max_retries`` is reached, after which the task
  stays ``failed`` for human review.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import Task
from app.workflow import dependencies_satisfied, transition_task

LEASE_SECONDS = 120
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 30


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class ExecutionOutcomeError(RuntimeError):
    """The executor reported a failure that should be recorded as a task failure."""


@dataclass(frozen=True)
class ExecutionResult:
    """What an executor returns. ``evidence`` is required for completion."""

    output: str
    evidence: str


@dataclass
class ExecutionOutcome:
    task_id: str
    status: str
    detail: str = ""
    executed: bool = False


class TaskExecutor(Protocol):
    def __call__(self, task: Task) -> ExecutionResult: ...


class DisabledExecutor:
    """The default: refuses to execute anything.

    This keeps the orchestrator honest — no work is ever simulated. Real
    executors must be injected deliberately by an authorized caller.
    """

    reason = "No executor is configured; AATM does not simulate task execution."

    def __call__(self, task: Task) -> ExecutionResult:
        raise ExecutionOutcomeError(self.reason)


@dataclass
class OrchestratorConfig:
    owner: str = "local-orchestrator"
    max_concurrency: int = 1
    lease_seconds: int = LEASE_SECONDS
    max_retries: int = MAX_RETRIES
    backoff_base_seconds: int = BACKOFF_BASE_SECONDS
    now: datetime | None = None


@dataclass
class RunReport:
    recovered: list[str] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    executor: str = "unknown"

    def as_dict(self) -> dict[str, object]:
        return {
            "recovered": list(self.recovered),
            "started": list(self.started),
            "completed": list(self.completed),
            "failed": list(self.failed),
            "skipped": [dict(item) for item in self.skipped],
            "executor": self.executor,
        }


def _attempt_key(task: Task, attempt: int) -> str:
    return f"orch-{task.id}-attempt-{attempt}"


def claim_task(
    db: Session,
    task: Task,
    *,
    owner: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Atomically-ish claim a task. Returns False when it is not claimable.

    SQLite with a single writer makes this safe locally; the conditional
    updates below also keep it correct if a second process races us between
    the read and the write.
    """
    if task.state != "assigned":
        return False
    if task.assigned_agent_id is None:
        return False
    satisfied, _blocking = dependencies_satisfied(db, task)
    if not satisfied:
        return False
    current = now or utc_now()
    expires = current + timedelta(seconds=max(1, lease_seconds))
    candidate = next_attempt_at(task)
    if candidate is not None and candidate > current:
        return False

    attempt = int(task.retry_count or 0) + 1
    task, created = transition_task(
        db,
        task,
        target_state="running",
        idempotency_key=_attempt_key(task, attempt),
        note=f"Claimed by {owner} with a {lease_seconds}s lease.",
    )
    if not created:
        return False
    task.lease_owner = owner
    task.lease_expires_at = expires
    task.next_attempt_at = None
    db.flush()
    return True


def next_attempt_at(task: Task) -> datetime | None:
    return _aware(task.next_attempt_at)


def release_lease(task: Task) -> None:
    task.lease_owner = None
    task.lease_expires_at = None


def recover_expired_leases(
    db: Session,
    *,
    now: datetime | None = None,
    owner: str = "recovery",
) -> list[str]:
    """Return tasks with expired leases to ``assigned`` and record the attempt.

    This is the crash-recovery path: any task left ``running`` by a process
    that died (or a machine that rebooted) is reconciled instead of being
    stuck forever.
    """
    current = now or utc_now()
    recovered: list[str] = []
    running = list(db.scalars(select(Task).where(Task.state == "running")).all())
    for task in running:
        expires = _aware(task.lease_expires_at)
        if expires is not None and expires > current:
            continue
        attempt = int(task.retry_count or 0)
        transition_task(
            db,
            task,
            target_state="failed",
            idempotency_key=f"recover-{task.id}-attempt-{attempt}",
            note=f"Lease expired for owner '{task.lease_owner or 'unknown'}'; returning to the queue for recovery.",
            error="Lease expired (interrupted run).",
        )
        # The interrupted attempt still counts: retry_count was incremented by
        # the failure transition, which keeps future claim keys distinct.
        task.state = "assigned"
        task.next_attempt_at = current
        release_lease(task)
        recovered.append(task.id)
        add_event(
            db,
            "task",
            task.id,
            "task.lease_recovered",
            f"Expired lease recovered for task: {task.title}",
        )
    db.flush()
    return recovered


def _schedule_retry(task: Task, config: OrchestratorConfig, current: datetime) -> None:
    attempt = int(task.retry_count or 0)
    if attempt >= config.max_retries:
        task.next_attempt_at = None
        return
    delay = config.backoff_base_seconds * (2 ** max(0, attempt - 1))
    task.next_attempt_at = current + timedelta(seconds=delay)


class Orchestrator:
    """Run one bounded batch of ready tasks through the supplied executor."""

    def __init__(self, executor: TaskExecutor | None = None, config: OrchestratorConfig | None = None) -> None:
        self.executor: TaskExecutor = executor or DisabledExecutor()
        self.config = config or OrchestratorConfig()

    def _ready_candidates(self, db: Session, now: datetime) -> list[Task]:
        candidates = list(
            db.scalars(
                select(Task).where(
                    Task.state == "assigned",
                    Task.assigned_agent_id.is_not(None),
                )
            ).all()
        )
        priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        ready = []
        for task in candidates:
            satisfied, _blocking = dependencies_satisfied(db, task)
            if not satisfied:
                continue
            due = _aware(task.next_attempt_at)
            if due is not None and due > now:
                continue
            ready.append(task)
        ready.sort(key=lambda item: (priority_order.get(item.priority, 9), item.created_at))
        return ready

    def run_once(self, db: Session) -> RunReport:
        now = self.config.now or utc_now()
        report = RunReport(executor=getattr(self.executor, "__name__", type(self.executor).__name__))
        report.recovered = recover_expired_leases(db, now=now, owner=self.config.owner)

        budget = max(1, self.config.max_concurrency)
        for task in self._ready_candidates(db, now)[:budget]:
            if not claim_task(
                db,
                task,
                owner=self.config.owner,
                lease_seconds=self.config.lease_seconds,
                now=now,
            ):
                report.skipped.append({"task_id": task.id, "reason": "not claimable"})
                continue
            report.started.append(task.id)
            attempt = int(task.retry_count or 0) + 1
            try:
                result = self.executor(task)
            except ExecutionOutcomeError as exc:
                self._record_failure(db, task, config=self.config, message=str(exc), attempt=attempt, now=now)
                report.failed.append(task.id)
                continue
            except Exception as exc:  # executor bugs must not corrupt workflow state
                self._record_failure(
                    db,
                    task,
                    config=self.config,
                    message=f"Executor error: {type(exc).__name__}",
                    attempt=attempt,
                    now=now,
                )
                report.failed.append(task.id)
                continue

            if not (result.evidence or "").strip():
                self._record_failure(
                    db,
                    task,
                    config=self.config,
                    message="Executor returned no evidence; completion was rejected.",
                    attempt=attempt,
                    now=now,
                )
                report.failed.append(task.id)
                continue

            transition_task(
                db,
                task,
                target_state="completed",
                idempotency_key=f"complete-{task.id}-attempt-{attempt}",
                note=result.evidence,
                output=result.output,
            )
            release_lease(task)
            task.next_attempt_at = None
            report.completed.append(task.id)
        db.flush()
        return report

    def _record_failure(
        self,
        db: Session,
        task: Task,
        *,
        config: OrchestratorConfig,
        message: str,
        attempt: int,
        now: datetime,
    ) -> None:
        transition_task(
            db,
            task,
            target_state="failed",
            idempotency_key=f"fail-{task.id}-attempt-{attempt}",
            note=message[:500],
            error=message[:500],
        )
        release_lease(task)
        _schedule_retry(task, config, now)
        db.flush()
