"""Durable task orchestration with leases, bounded concurrency and recovery.

Design guarantees (all verified by tests):

* **No provider coupling.** Execution happens through an injectable
  ``TaskExecutor`` protocol. The default executor refuses to run; the opt-in
  local executor is supplied by the HTTP adapter, not constructed here.
* **Leases, not lock-in-process.** A claim writes ``lease_owner`` and
  ``lease_expires_at`` so a crashed process cannot permanently own a task.
* **Bounded parallel dispatch.** ``max_concurrency`` caps claims in one run.
  Executor calls use a bounded thread pool (one worker at a cap of one); only a
  cap above one allows parallel task execution. Workflow/database writes and
  periodic lease renewals stay on the orchestrator thread. The HTTP adapter
  serializes run requests within one app process; this is not a distributed
  multi-process semaphore.
* **Crash recovery.** ``recover_expired_leases`` reconciles tasks whose lease
  expired: the task returns to ``assigned`` and the attempt is recorded, so a
  kill -9 mid-run cannot leave work stuck in ``running`` forever.
* **Replay safety.** Every state change goes through the workflow service with
  a deterministic idempotency key derived from the task id and attempt number.
* **Retry policy.** Failures increment ``retry_count`` and set a backoff
  ``next_attempt_at`` until ``max_retries`` is reached, after which the task
  stays ``failed`` for human review.
"""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.audit import add_event
from app.cancellation import honour_all as honour_cancellations
from app.models import Task, TaskTransition
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


class ExecutionCancelled(RuntimeError):
    """An in-flight execution was stopped because the task was cancelled.

    Separate from ``ExecutionOutcomeError`` on purpose: a withdrawal is not
    evidence about the work, so it must not increment ``retry_count`` or be
    reported as a failed attempt.
    """


class ExecutionLeaseLost(RuntimeError):
    """An in-flight execution was stopped after its task lease was lost."""


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
    heartbeat_callback: Callable[[], None] | None = None


@dataclass
class RunReport:
    recovered: list[str] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    executor: str = "unknown"

    def as_dict(self) -> dict[str, object]:
        return {
            "recovered": list(self.recovered),
            "started": list(self.started),
            "completed": list(self.completed),
            "failed": list(self.failed),
            "skipped": [dict(item) for item in self.skipped],
            "cancelled": list(self.cancelled),
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
    """Claim a task with a conditional database update.

    Readiness and dependency checks are advisory; the final UPDATE is a
    compare-and-set on ``state='assigned'`` so two processes that selected the
    same candidate cannot both own it. The transition/audit rows are written in
    the same transaction as the lease. API run requests remain serialized until
    shared permit scheduling and workspace-mutation exclusion are wired in.
    """
    if task.state != "assigned" or task.assigned_agent_id is None:
        return False
    satisfied, _blocking = dependencies_satisfied(db, task)
    if not satisfied:
        return False
    current = now or utc_now()
    candidate = next_attempt_at(task)
    if candidate is not None and candidate > current:
        return False

    expires = current + timedelta(seconds=max(1, lease_seconds))
    attempt = int(task.retry_count or 0) + 1
    note = f"Claimed by {owner} with a {lease_seconds}s lease."
    result = db.execute(
        update(Task)
        .where(
            Task.id == task.id,
            Task.state == "assigned",
            Task.assigned_agent_id.is_not(None),
            or_(Task.next_attempt_at.is_(None), Task.next_attempt_at <= current),
        )
        .values(
            state="running",
            lease_owner=owner,
            lease_expires_at=expires,
            next_attempt_at=None,
            error=None,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return False

    # Keep the caller's already-loaded object coherent without sharing it with
    # worker threads. All durable writes remain in this control-thread session.
    task.state = "running"
    task.lease_owner = owner
    task.lease_expires_at = expires
    task.next_attempt_at = None
    task.error = None
    db.add(
        TaskTransition(
            task_id=task.id,
            from_state="assigned",
            to_state="running",
            idempotency_key=_attempt_key(task, attempt),
            note=note,
            created_at=utc_now(),
        )
    )
    add_event(db, "task", task.id, "task.state_changed", f"Task assigned → running: {task.title}")
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


def _honour_single_cancel(db: Session, task: Task) -> list[str]:
    """Move one task to ``cancelled`` after its executor stopped mid-run.

    The session is created with ``expire_on_commit=False``, so the object in hand
    still carries the pre-cancellation values: the request was written by another
    connection while the executor ran. Without an explicit refresh, ``honour_cancel``
    reads ``cancel_requested_at = None`` and reports "no pending request", leaving a
    stopped task stuck in ``running`` forever.
    """
    from app.cancellation import CancelError, honour_cancel

    try:
        db.refresh(task)
    except Exception:
        return []
    if task.cancel_requested_at is None:
        return []
    try:
        outcome = honour_cancel(db, task)
    except CancelError:
        return []
    return [task.id] if outcome.get("cancelled") else []


def _schedule_retry(task: Task, config: OrchestratorConfig, current: datetime) -> None:
    attempt = int(task.retry_count or 0)
    if attempt >= config.max_retries:
        task.next_attempt_at = None
        return
    delay = config.backoff_base_seconds * (2 ** max(0, attempt - 1))
    task.next_attempt_at = current + timedelta(seconds=delay)


def _lock_live_task_lease(
    db: Session,
    task: Task,
    *,
    owner: str,
    now: datetime,
) -> bool:
    """Take a conditional row lock before recording an executor outcome.

    A worker that has expired or lost its lease may finish its local command,
    but it must not overwrite the newer owner's workflow state. The no-op
    owner update locks the matching row until the caller commits its transition.
    """
    result = db.execute(
        update(Task)
        .where(
            Task.id == task.id,
            Task.state == "running",
            Task.lease_owner == owner,
            Task.lease_expires_at.is_not(None),
            Task.lease_expires_at > now,
        )
        .values(lease_owner=Task.lease_owner)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.expire(task)
        return False
    db.refresh(task)
    return task.state == "running" and task.lease_owner == owner


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
        # Cancellations are honoured before any claim, so a cancelled task is
        # never started, and never after it is cancelled.
        cancel_report = honour_cancellations(db)
        report.cancelled = [item["task_id"] for item in cancel_report["applied"]]

        # Zero is meaningful for the opt-in adaptive policy: inspect/recover but
        # dispatch nothing when all recommended slots are occupied.
        budget = max(0, self.config.max_concurrency)
        dispatch: list[Task] = []
        claimed_projects: set[str] = set()
        for task in self._ready_candidates(db, now):
            if len(dispatch) >= budget:
                break
            # Tasks may share a project dispatch slot only when their executor
            # can prove that each gets a separate working directory. Otherwise
            # project-level serialization is the safe default.
            dispatch_group = getattr(self.executor, "dispatch_group", None)
            try:
                workspace_key = dispatch_group(task) if callable(dispatch_group) else (task.project_id or f"task:{task.id}")
            except Exception:
                workspace_key = task.project_id or f"task:{task.id}"
            if workspace_key in claimed_projects:
                report.skipped.append({"task_id": task.id, "reason": "another task from this project is in the same dispatch batch"})
                continue
            claimed_projects.add(workspace_key)
            dispatch.append(task)

        claimed: list[tuple[Task, int]] = []
        for task in dispatch:
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
            claimed.append((task, int(task.retry_count or 0) + 1))

        if not claimed:
            db.flush()
            return report

        # Commit all leases before starting any executor. No database write lock
        # is held during subprocess work, so cancellation and other local requests
        # can proceed. The main Session remains confined to this thread.
        db.commit()
        # Worker threads each load their own ORM instance/session. The main
        # session is never shared across threads; workflow/database writes,
        # including lease heartbeats, stay on the orchestrator thread.
        worker_factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)

        def execute_in_worker(task_id: str) -> ExecutionResult:
            with worker_factory() as worker_db:
                worker_task = worker_db.get(Task, task_id)
                if worker_task is None:
                    raise LookupError("Claimed task vanished before execution.")
                return self.executor(worker_task)

        outcomes_by_id: dict[str, ExecutionResult | Exception] = {}
        runnable: list[tuple[Task, int]] = []
        prepare_task = getattr(self.executor, "prepare_task", None)
        for task, attempt in claimed:
            try:
                if callable(prepare_task):
                    prepare_task(task)
                runnable.append((task, attempt))
            except Exception as exc:
                outcomes_by_id[task.id] = exc

        if runnable:
            # Filesystem/Git preparation above is serial on the control thread.
            # Renew just-prepared leases before starting their worker threads.
            expires = utc_now() + timedelta(seconds=max(1, self.config.lease_seconds))
            for task, _attempt in runnable:
                db.execute(
                    update(Task)
                    .where(
                        Task.id == task.id,
                        Task.state == "running",
                        Task.lease_owner == self.config.owner,
                    )
                    .values(lease_expires_at=expires)
                )
            db.commit()
            if self.config.heartbeat_callback is not None:
                self.config.heartbeat_callback()

            with ThreadPoolExecutor(max_workers=min(budget, len(runnable)), thread_name_prefix="aatm-task") as pool:
                pending = {
                    pool.submit(execute_in_worker, task.id): task.id
                    for task, _attempt in runnable
                }
                heartbeat_interval = max(0.1, max(1, self.config.lease_seconds) / 3)
                while pending:
                    completed, _ = wait(pending, timeout=heartbeat_interval, return_when=FIRST_COMPLETED)
                    for future in completed:
                        task_id = pending.pop(future)
                        try:
                            outcomes_by_id[task_id] = future.result()
                        except Exception as exc:
                            outcomes_by_id[task_id] = exc

                    if pending:
                        # Long-running work must not be mistaken for a crashed
                        # worker. Renew only leases still owned and running; never
                        # overwrite a lease another process has recovered/reclaimed.
                        expires = utc_now() + timedelta(seconds=max(1, self.config.lease_seconds))
                        for task_id in pending.values():
                            db.execute(
                                update(Task)
                                .where(
                                    Task.id == task_id,
                                    Task.state == "running",
                                    Task.lease_owner == self.config.owner,
                                )
                                .values(lease_expires_at=expires)
                            )
                        db.commit()
                        if self.config.heartbeat_callback is not None:
                            self.config.heartbeat_callback()

        # Preserve claim-order reporting, independent of completion order.
        outcomes = [outcomes_by_id[task.id] for task, _attempt in claimed]

        for (task, attempt), outcome in zip(claimed, outcomes, strict=True):
            if not _lock_live_task_lease(
                db,
                task,
                owner=self.config.owner,
                now=utc_now(),
            ):
                report.skipped.append({"task_id": task.id, "reason": "task lease expired or ownership changed before result recording"})
                continue

            if isinstance(outcome, ExecutionCancelled):
                # Honour the request through the validated workflow rather than
                # marking a failure; a cancelled task is not a broken one.
                report.cancelled.extend(_honour_single_cancel(db, task))
                continue
            if isinstance(outcome, ExecutionOutcomeError):
                self._record_failure(db, task, config=self.config, message=str(outcome), attempt=attempt, now=now)
                report.failed.append(task.id)
                continue
            if isinstance(outcome, Exception):  # executor bugs must not corrupt workflow state
                self._record_failure(
                    db,
                    task,
                    config=self.config,
                    message=f"Executor error: {type(outcome).__name__}",
                    attempt=attempt,
                    now=now,
                )
                report.failed.append(task.id)
                continue

            if not (outcome.evidence or "").strip():
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
                note=outcome.evidence,
                output=outcome.output,
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
