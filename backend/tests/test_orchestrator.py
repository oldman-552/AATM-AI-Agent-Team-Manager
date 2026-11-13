"""Orchestrator tests using an injected fake executor (never a provider)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import AuditEvent, Task, TaskTransition
from app.orchestrator import (
    DisabledExecutor,
    ExecutionOutcomeError,
    ExecutionResult,
    Orchestrator,
    OrchestratorConfig,
    claim_task,
    recover_expired_leases,
)

UTC = timezone.utc


@pytest.fixture
def app_client() -> TestClient:
    app = create_app("sqlite://", allowed_hosts=["testserver"])
    with TestClient(app) as client:
        yield client


def session_of(client: TestClient):
    return client.app.state.session_factory()


def make_agent(client: TestClient, name: str = "Worker") -> str:
    return client.post("/api/v1/agents", json={"name": name, "role": "Backend Developer"}).json()["id"]


def make_task(client: TestClient, agent_id: str, **extra) -> str:
    payload = {"title": "Orchestrated task", "assigned_agent_id": agent_id}
    payload.update(extra)
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def fake_executor(label: str = "ok"):
    calls: list[str] = []

    def execute(task: Task) -> ExecutionResult:
        calls.append(task.id)
        return ExecutionResult(output=f"{label}:{task.title}", evidence="Fake executor produced deterministic evidence.")

    execute.calls = calls  # type: ignore[attr-defined]
    execute.__name__ = "fake_executor"
    return execute


def test_default_executor_refuses_to_run_and_records_failure(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)

    with session_of(app_client) as db:
        report = Orchestrator().run_once(db)
        db.commit()
        task = db.get(Task, task_id)
        assert report.started == [task_id]
        assert report.failed == [task_id]
        assert task.state == "failed"
        assert "does not simulate" in (task.error or "")
        assert task.lease_owner is None
        assert task.next_attempt_at is not None


def test_fake_executor_completes_task_with_evidence(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)
    executor = fake_executor()

    with session_of(app_client) as db:
        report = Orchestrator(executor).run_once(db)
        db.commit()
        task = db.get(Task, task_id)
        assert report.completed == [task_id]
        assert task.state == "completed"
        assert task.output == f"ok:{task.title}"
        assert task.lease_owner is None
        transitions = db.scalars(
            select(TaskTransition).where(TaskTransition.task_id == task_id).order_by(TaskTransition.created_at)
        ).all()
        assert [(t.from_state, t.to_state) for t in transitions] == [
            ("assigned", "running"),
            ("running", "completed"),
        ]
    assert executor.calls == [task_id]  # type: ignore[attr-defined]


def test_results_without_evidence_are_rejected(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)

    def no_evidence(task: Task) -> ExecutionResult:
        return ExecutionResult(output="did something", evidence="   ")

    with session_of(app_client) as db:
        report = Orchestrator(no_evidence).run_once(db)
        db.commit()
        task = db.get(Task, task_id)
        assert report.failed == [task_id]
        assert task.state == "failed"
        assert "evidence" in (task.error or "").lower()


def test_executor_exceptions_do_not_corrupt_state(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)

    def exploding(task: Task) -> ExecutionResult:
        raise ValueError("boom with a secret api_key=abc123")

    with session_of(app_client) as db:
        Orchestrator(exploding).run_once(db)
        db.commit()
        task = db.get(Task, task_id)
        assert task.state == "failed"
        # Only the exception type is recorded; the message is never propagated.
        assert task.error == "Executor error: ValueError"


def test_bounded_concurrency_limits_started_tasks(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_ids = [make_task(app_client, agent, title=f"Task {index}") for index in range(3)]
    executor = fake_executor()

    with session_of(app_client) as db:
        report = Orchestrator(executor, OrchestratorConfig(max_concurrency=2)).run_once(db)
        db.commit()
        assert len(report.started) == 2
        assert len(report.completed) == 2
        assert len(executor.calls) == 2  # type: ignore[attr-defined]
        states = {task_id: db.get(Task, task_id).state for task_id in task_ids}
        assert sorted(states.values()) == ["assigned", "completed", "completed"]


def test_dependencies_block_dispatch(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    first = make_task(app_client, agent, title="First")
    second = make_task(app_client, agent, title="Second", dependencies=[first])
    executor = fake_executor()

    with session_of(app_client) as db:
        report = Orchestrator(executor, OrchestratorConfig(max_concurrency=5)).run_once(db)
        db.commit()
        assert report.started == [first]
        assert db.get(Task, second).state == "assigned"

    with session_of(app_client) as db:
        report = Orchestrator(executor, OrchestratorConfig(max_concurrency=5)).run_once(db)
        db.commit()
        assert report.started == [second]
        assert db.get(Task, second).state == "completed"


def test_expired_lease_is_recovered_and_retried(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)
    past = datetime.now(UTC) - timedelta(minutes=10)

    with session_of(app_client) as db:
        task = db.get(Task, task_id)
        assert claim_task(db, task, owner="crashed-worker", lease_seconds=60, now=past)
        db.commit()
        assert task.state == "running"
        assert task.lease_owner == "crashed-worker"

    with session_of(app_client) as db:
        recovered = recover_expired_leases(db)
        db.commit()
        task = db.get(Task, task_id)
        assert recovered == [task_id]
        assert task.state == "assigned"
        assert task.lease_owner is None
        assert task.next_attempt_at is not None

    executor = fake_executor()
    with session_of(app_client) as db:
        report = Orchestrator(executor).run_once(db)
        db.commit()
        assert report.completed == [task_id]
        assert db.get(Task, task_id).state == "completed"


def test_active_lease_is_not_stolen(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)

    with session_of(app_client) as db:
        task = db.get(Task, task_id)
        assert claim_task(db, task, owner="worker-a", lease_seconds=300)
        db.commit()

    with session_of(app_client) as db:
        task = db.get(Task, task_id)
        assert claim_task(db, task, owner="worker-b", lease_seconds=300) is False
        assert recover_expired_leases(db) == []


def test_retry_backoff_and_max_retries(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)

    def always_fails(task: Task) -> ExecutionResult:
        raise ExecutionOutcomeError("deliberate failure")

    base = datetime.now(UTC)
    with session_of(app_client) as db:
        for attempt in range(3):
            now = base + timedelta(minutes=attempt * 10)
            report = Orchestrator(
                always_fails,
                OrchestratorConfig(max_retries=2, backoff_base_seconds=60, now=now),
            ).run_once(db)
            db.commit()
            if attempt < 2:
                assert report.failed == [task_id]
                task = db.get(Task, task_id)
                task.state = "assigned"
                task.next_attempt_at = None
                db.commit()
        task = db.get(Task, task_id)
        assert int(task.retry_count) == 3
        assert task.next_attempt_at is None  # retries exhausted


def test_retry_not_dispatched_before_backoff_elapses(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)

    def fails_once(task: Task) -> ExecutionResult:
        raise ExecutionOutcomeError("transient")

    now = datetime.now(UTC)
    with session_of(app_client) as db:
        Orchestrator(fails_once, OrchestratorConfig(backoff_base_seconds=600, now=now)).run_once(db)
        db.commit()
        task = db.get(Task, task_id)
        task.state = "assigned"
        db.commit()

        executor = fake_executor()
        report = Orchestrator(executor, OrchestratorConfig(now=now + timedelta(seconds=30))).run_once(db)
        db.commit()
        assert report.started == []

        later = Orchestrator(executor, OrchestratorConfig(now=now + timedelta(seconds=900))).run_once(db)
        db.commit()
        assert later.completed == [task_id]


def test_orchestrator_writes_audit_events(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    make_task(app_client, agent)
    with session_of(app_client) as db:
        Orchestrator(fake_executor()).run_once(db)
        db.commit()
        events = db.scalars(select(AuditEvent)).all()
        types = [event.event_type for event in events]
        assert types.count("task.state_changed") == 2


def test_recovery_survives_process_restart(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'orch.sqlite3').as_posix()}"
    kwargs = {"allowed_hosts": ["testserver"]}

    with TestClient(create_app(database_url, **kwargs)) as client:
        agent = make_agent(client)
        task_id = make_task(client, agent)
        past = datetime.now(UTC) - timedelta(minutes=5)
        with session_of(client) as db:
            assert claim_task(db, db.get(Task, task_id), owner="dead", lease_seconds=60, now=past)
            db.commit()

    with TestClient(create_app(database_url, **kwargs)) as restarted:
        with session_of(restarted) as db:
            recovered = recover_expired_leases(db)
            db.commit()
            assert recovered == [task_id]
            assert db.get(Task, task_id).state == "assigned"


def test_disabled_executor_is_explicitly_labelled() -> None:
    executor = DisabledExecutor()
    with pytest.raises(ExecutionOutcomeError) as excinfo:
        executor(Task(title="x"))  # type: ignore[arg-type]
    assert "does not simulate" in str(excinfo.value)


def test_orchestrator_api_executes_nothing_by_default(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    task_id = make_task(app_client, agent)
    past = datetime.now(UTC) - timedelta(minutes=5)

    with session_of(app_client) as db:
        assert claim_task(db, db.get(Task, task_id), owner="dead-worker", lease_seconds=60, now=past)
        db.commit()

    status = app_client.get("/api/v1/orchestrator/status")
    assert status.status_code == 200
    body = status.json()
    assert body["executor"]["configured"] is False
    assert "cannot start a run" in body["note"]
    assert body["counts"]["running"] == 1
    assert body["counts"]["expired_leases"] == 1
    assert body["leases"][0]["lease_owner"] == "dead-worker"

    recovered = app_client.post("/api/v1/orchestrator/recover")
    assert recovered.status_code == 200
    assert recovered.json()["recovered"] == [task_id]
    assert app_client.get("/api/v1/tasks").json()[0]["state"] == "assigned"

    # Recovery is idempotent. A dispatch endpoint now exists, but by default it
    # refuses: the guarantee this test protects is that a default build cannot
    # start a run, not that the route is absent. Asserting 404 would pass again
    # the day someone deletes the route, which is the weaker check.
    assert app_client.post("/api/v1/orchestrator/recover").json()["count"] == 0
    refused = app_client.post("/api/v1/orchestrator/run")
    assert refused.status_code == 409
    assert "AATM_EXECUTION_ENABLED" in refused.json()["detail"]


def test_claim_rejects_unassigned_and_replay_claim(app_client: TestClient) -> None:
    agent = make_agent(app_client)
    unassigned = app_client.post("/api/v1/tasks", json={"title": "No owner"}).json()["id"]
    assigned_id = make_task(app_client, agent)

    with session_of(app_client) as db:
        assert claim_task(db, db.get(Task, unassigned), owner="w", lease_seconds=60) is False
        task = db.get(Task, assigned_id)
        assert claim_task(db, task, owner="w", lease_seconds=60) is True
        db.commit()

    with session_of(app_client) as db:
        # A second claim on an already-running task is refused (no double dispatch).
        assert claim_task(db, db.get(Task, assigned_id), owner="w2", lease_seconds=60) is False
