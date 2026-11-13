"""Tests for the real local executor.

Each test targets a specific way a subprocess runner goes wrong, not merely that
a happy path works: a task naming a hostile command, an escape from the
workspace, a leaked secret, a hung process, an orphaned grandchild, and a
cancellation recorded as a failure.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import build_engine, make_session_factory
from app.main import create_app
from app.execution import (
    ExecutionError,
    LocalProcessExecutor,
    command_name_for,
    load_commands,
)
from app.models import Base, Project, ProjectWorkspace, Task
from app.orchestrator import ExecutionCancelled, ExecutionOutcomeError, Orchestrator, OrchestratorConfig


@pytest.fixture
def client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
    with TestClient(create_app(url, allowed_hosts=["testserver"])) as tc:
        yield tc


class Fixture:
    """The factory plus the paths, so tests do not reach into session state."""

    def __init__(self, factory, project_id, project_dir, workspace_root):
        self.factory = factory
        self.project_id = project_id
        self.project_dir = project_dir
        self.workspace_root = workspace_root

    def __call__(self):
        return self.factory()


@pytest.fixture
def env(tmp_path):
    engine = build_engine(f"sqlite:///{(tmp_path / 'exec.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        project = Project(name="Runner", description="")
        session.add(project)
        session.flush()
        workspace_root = tmp_path / "workspaces"
        project_dir = workspace_root / "runner"
        project_dir.mkdir(parents=True)
        session.add(
            ProjectWorkspace(
                project_id=project.id,
                root_path=str(workspace_root),
                workspace_path=str(project_dir),
                status="active",
            )
        )
        session.commit()
        fixture = Fixture(factory, project.id, project_dir, workspace_root)
    yield fixture


def make_task(env, project_id, criteria):
    with env() as session:
        task = Task(
            project_id=project_id,
            title="Run something",
            description="",
            acceptance_criteria=list(criteria),
            priority="normal",
            state="assigned",
        )
        session.add(task)
        session.commit()
        return task.id


def write_commands(project_dir, commands):
    target = project_dir / ".aatm"
    target.mkdir(exist_ok=True)
    (target / "exec.json").write_text(json.dumps(commands), encoding="utf-8")


def load_task(env, task_id):
    with env() as session:
        return session.get(Task, task_id)


# -- command selection -----------------------------------------------------

def test_command_name_requires_exactly_one_run_criterion(env):
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    none_named = Task(project_id=project_id, title="t", description="", acceptance_criteria=["it works"], state="assigned")
    with pytest.raises(ExecutionError, match="names no command"):
        command_name_for(none_named)

    two = Task(
        project_id=project_id, title="t", description="",
        acceptance_criteria=["run:one", "run:two"], state="assigned",
    )
    with pytest.raises(ExecutionError, match="exactly one"):
        command_name_for(two)

    ok = Task(project_id=project_id, title="t", description="", acceptance_criteria=["Run: build"], state="assigned")
    assert command_name_for(ok) == "build"


# -- the safety rules ------------------------------------------------------

def test_a_task_naming_a_path_instead_of_a_program_is_refused(env):
    """The database must never be able to point at an arbitrary executable."""
    project_dir = env.project_dir
    write_commands(project_dir, {"evil": {"argv": ["./evil.sh"]}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:evil"])
    executor = LocalProcessExecutor(env.factory)
    with pytest.raises(ExecutionError, match="Only bare program names"):
        executor.resolve(load_task(env, task_id))


def test_a_program_outside_the_allow_list_is_refused(env):
    project_dir = env.project_dir
    write_commands(project_dir, {"sneaky": {"argv": ["bash", "-c", "echo hi"]}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:sneaky"])
    executor = LocalProcessExecutor(env.factory)
    with pytest.raises(ExecutionError, match="not allow-listed"):
        executor.resolve(load_task(env, task_id))


def test_a_missing_workspace_is_refused_rather_than_falling_back(env):
    """No workspace means no cwd. Running in the app directory would be worse."""
    project_id = None
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    other = None
    with env() as session:
        other = Project(name="No workspace", description="")
        session.add(other)
        session.commit()
        other_id = other.id
    task_id = make_task(env, other_id, ["run:anything"])
    executor = LocalProcessExecutor(env.factory)
    with pytest.raises(ExecutionError, match="no workspace"):
        executor.resolve(load_task(env, task_id))
    assert project_id is not None


def test_secrets_are_not_inherited_by_the_child(env, monkeypatch):
    """A provider key in the parent environment must not reach the subprocess."""
    monkeypatch.setenv("AATM_AUTH_TOKEN", "super-secret-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    project_dir = env.project_dir
    write_commands(
        project_dir,
        {"env": {"argv": ["python3", "-c", "import os; print(sorted(os.environ))"]}},
    )
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:env"])
    executor = LocalProcessExecutor(env.factory)
    result = executor(load_task(env, task_id))
    assert "AATM_AUTH_TOKEN" not in result.output
    assert "OPENAI_API_KEY" not in result.output
    assert "PATH" in result.output


def test_a_command_runs_in_the_project_workspace(env):
    project_dir = env.project_dir
    write_commands(project_dir, {"pwd": {"argv": ["python3", "-c", "import os; print(os.getcwd())"]}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:pwd"])
    executor = LocalProcessExecutor(env.factory)
    result = executor(load_task(env, task_id))
    assert str(project_dir) in result.output
    assert result.evidence


def test_a_hung_command_is_killed_at_its_timeout(env):
    project_dir = env.project_dir
    write_commands(project_dir, {"hang": {"argv": ["python3", "-c", "import time; time.sleep(30)"], "timeout_seconds": 1}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:hang"])
    executor = LocalProcessExecutor(env, cancel_poll_seconds=0.1)
    started = time.monotonic()
    with pytest.raises(ExecutionOutcomeError, match="exceeded its 1s timeout"):
        executor(load_task(env, task_id))
    assert time.monotonic() - started < 15


def test_a_nonzero_exit_is_a_failure_not_a_success(env):
    project_dir = env.project_dir
    write_commands(project_dir, {"fail": {"argv": ["python3", "-c", "import sys; sys.exit(3)"]}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:fail"])
    executor = LocalProcessExecutor(env.factory)
    with pytest.raises(ExecutionOutcomeError, match="exited with status 3"):
        executor(load_task(env, task_id))


def test_large_output_is_truncated_not_unbounded(env):
    project_dir = env.project_dir
    write_commands(
        project_dir,
        {"spam": {"argv": ["python3", "-c", "print('x' * 200000)"]}},
    )
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:spam"])
    executor = LocalProcessExecutor(env, max_output_bytes=2048)
    result = executor(load_task(env, task_id))
    assert len(result.output) <= 2048
    assert "truncated" in result.evidence


def test_a_missing_command_file_is_an_error_not_silence(env):
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:anything"])
    executor = LocalProcessExecutor(env.factory)
    with pytest.raises(ExecutionError, match="No command file"):
        executor.resolve(load_task(env, task_id))


def test_invalid_json_lists_the_file_rather_than_crashing(env):
    project_dir = env.project_dir
    (project_dir / ".aatm").mkdir(exist_ok=True)
    (project_dir / ".aatm" / "exec.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ExecutionError, match="not valid JSON"):
        load_commands(project_dir)


# -- cancellation ----------------------------------------------------------

def test_cancellation_kills_the_process_and_does_not_count_as_failure(env):
    """A withdrawal is not evidence about the work, so it must not fail the task."""
    project_dir = env.project_dir
    write_commands(project_dir, {"slow": {"argv": ["python3", "-c", "import time; time.sleep(30)"], "timeout_seconds": 60}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:slow"])
    executor = LocalProcessExecutor(env, cancel_poll_seconds=0.1)

    def cancel_soon():
        time.sleep(0.6)
        with env() as session:
            task = session.get(Task, task_id)
            task.cancel_requested_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            task.cancel_reason = "operator changed their mind"
            session.commit()

    import threading

    worker = threading.Thread(target=cancel_soon)
    worker.start()
    started = time.monotonic()
    with pytest.raises(ExecutionCancelled):
        executor(load_task(env, task_id))
    worker.join()
    assert time.monotonic() - started < 15


# -- end to end through the orchestrator -----------------------------------

def test_a_real_task_completes_with_recorded_output(env):
    """The point of the slice: one genuinely executed task, end to end."""
    project_dir = env.project_dir
    write_commands(project_dir, {"hello": {"argv": ["python3", "-c", "print('executed for real')"]}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:hello"])
    # The orchestrator only claims tasks assigned to an agent.
    from app.models import Agent

    with env() as session:
        agent = Agent(name="Runner", role="developer", provider="unconfigured")
        session.add(agent)
        session.commit()
        agent_id = agent.id
        task = session.get(Task, task_id)
        task.assigned_agent_id = agent_id
        session.commit()

    executor = LocalProcessExecutor(env.factory)
    with env() as session:
        report = Orchestrator(
            executor=executor,
            config=OrchestratorConfig(max_concurrency=1),
        ).run_once(session)
        session.commit()

    assert task_id in report.completed, report.as_dict()
    assert not report.failed
    with env() as session:
        task = session.get(Task, task_id)
        assert task.state == "completed"
        assert "executed for real" in (task.output or "")
        assert task.lease_owner is None


def test_a_failing_command_retries_then_stays_failed_for_review(env):
    project_dir = env.project_dir
    write_commands(project_dir, {"boom": {"argv": ["python3", "-c", "raise SystemExit(1)"]}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:boom"])
    from app.models import Agent

    with env() as session:
        agent = Agent(name="Runner", role="developer", provider="unconfigured")
        session.add(agent)
        session.commit()
        task = session.get(Task, task_id)
        task.assigned_agent_id = agent.id
        session.commit()

    executor = LocalProcessExecutor(env.factory)
    with env() as session:
        report = Orchestrator(
            executor=executor,
            config=OrchestratorConfig(max_concurrency=1, max_retries=0),
        ).run_once(session)
        session.commit()

    assert task_id in report.failed
    with env() as session:
        task = session.get(Task, task_id)
        assert task.state in {"failed", "assigned"}
        assert task.next_attempt_at is None, "no retry should be scheduled past the ceiling"
        assert task.lease_owner is None


def test_shutdown_terminates_live_processes(env):
    """An application shutdown must not leave orphans behind."""
    project_dir = env.project_dir
    write_commands(project_dir, {"slow": {"argv": ["python3", "-c", "import time; time.sleep(30)"], "timeout_seconds": 60}})
    with env() as session:
        project_id = session.scalars(select(Project.id)).first()
    task_id = make_task(env, project_id, ["run:slow"])
    executor = LocalProcessExecutor(env, cancel_poll_seconds=0.1)

    import threading

    errors: list[BaseException] = []

    def run():
        try:
            executor(load_task(env, task_id))
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.8)
    stopped = executor.shutdown(timeout_seconds=5)
    worker.join(timeout=10)
    assert stopped >= 1
    assert not worker.is_alive()


def test_orchestrator_records_a_cancelled_run_as_cancelled_not_failed(session_factory_unused=None):
    """End to end: the executor stops, and the orchestrator honours the request.

    Without the dedicated exception path this task would land in `failed` and
    increment retry_count — punishing an agent for the operator's decision.
    """
    import threading

    from app.db import build_engine, make_session_factory
    from app.execution import LocalProcessExecutor
    from app.models import Agent, Base, Project, ProjectWorkspace, Task
    from app.orchestrator import Orchestrator, OrchestratorConfig

    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    engine = build_engine(f"sqlite:///{(tmp / 'cancel.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)

    project_dir = tmp / "workspaces" / "runner"
    project_dir.mkdir(parents=True)
    (project_dir / ".aatm").mkdir()
    (project_dir / ".aatm" / "exec.json").write_text(
        json.dumps({"slow": {"argv": ["python3", "-c", "import time; time.sleep(30)"], "timeout_seconds": 60}}),
        encoding="utf-8",
    )
    with factory() as session:
        project = Project(name="Cancellable", description="")
        agent = Agent(name="Runner", role="developer", provider="unconfigured")
        session.add_all([project, agent])
        session.flush()
        session.add(
            ProjectWorkspace(
                project_id=project.id, root_path=str(tmp / "workspaces"),
                workspace_path=str(project_dir), status="active",
            )
        )
        task = Task(
            project_id=project.id, title="Long job", description="",
            acceptance_criteria=["run:slow"], priority="normal", state="assigned",
            assigned_agent_id=agent.id,
        )
        session.add(task)
        session.commit()
        task_id = task.id

    executor = LocalProcessExecutor(factory, cancel_poll_seconds=0.1)

    class CancellingExecutor:
        """Wraps the real executor, requesting cancellation mid-run."""

        def __call__(self, task):
            def cancel_soon():
                time.sleep(0.5)
                with factory() as session:
                    row = session.get(Task, task_id)
                    row.cancel_requested_at = __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    )
                    row.cancel_reason = "operator stopped it"
                    session.commit()

            worker = threading.Thread(target=cancel_soon)
            worker.start()
            try:
                return executor(task)
            finally:
                worker.join()

    with factory() as session:
        report = Orchestrator(
            executor=CancellingExecutor(),
            config=OrchestratorConfig(max_concurrency=1),
        ).run_once(session)
        session.commit()

    assert task_id in report.cancelled, report.as_dict()
    assert task_id not in report.failed
    with factory() as session:
        row = session.get(Task, task_id)
        assert row.state == "cancelled"
        assert row.retry_count == 0, "a cancellation must not add a retry penalty"
        assert row.lease_owner is None


# -- opt-in activation -----------------------------------------------------

def test_execution_is_off_by_default(monkeypatch):
    from app.execution import execution_enabled

    monkeypatch.delenv("AATM_EXECUTION_ENABLED", raising=False)
    assert execution_enabled() is False


def test_the_flag_accepts_the_obvious_spellings(monkeypatch):
    from app.execution import execution_enabled

    for spelling in ("1", "true", "YES", "on"):
        monkeypatch.setenv("AATM_EXECUTION_ENABLED", spelling)
        assert execution_enabled() is True
    for spelling in ("", "0", "false", "no", "maybe"):
        monkeypatch.setenv("AATM_EXECUTION_ENABLED", spelling)
        assert execution_enabled() is False


def test_the_environment_cannot_widen_the_allow_list(monkeypatch):
    """An env var is not a code-review boundary."""
    from app.execution import DEFAULT_ALLOWED_PROGRAMS, configured_programs

    monkeypatch.setenv("AATM_EXECUTION_PROGRAMS", "bash,rm,python3")
    allowed = configured_programs()
    assert "bash" not in allowed and "rm" not in allowed
    assert "python3" in allowed
    assert set(allowed).issubset(set(DEFAULT_ALLOWED_PROGRAMS))


def test_the_run_endpoint_refuses_when_disabled(client):
    """HTTP must not be able to switch execution on."""
    monkeypatch_free = client
    response = monkeypatch_free.post("/api/v1/orchestrator/run")
    assert response.status_code == 409
    assert "AATM_EXECUTION_ENABLED" in response.json()["detail"]


def test_run_endpoint_applies_opt_in_adaptive_dispatch_cap(client, monkeypatch):
    from app.resources import ResourceSnapshot

    monkeypatch.setenv("AATM_EXECUTION_ENABLED", "1")
    monkeypatch.setenv("AATM_ADAPTIVE_CONCURRENCY", "1")
    monkeypatch.setenv("AATM_MAX_CONCURRENCY", "4")
    snapshot = ResourceSnapshot(
        cpu_percent=96.0,
        load_average_1m=8.0,
        cpu_count=4,
        memory_total_mb=8000.0,
        memory_available_mb=400.0,
        memory_used_ratio=0.95,
        disk_total_gb=100.0,
        disk_free_gb=2.0,
        disk_used_ratio=0.98,
        measured_at="2026-11-13T00:00:00+00:00",
    )
    monkeypatch.setattr("app.adaptive_concurrency.sample_resources", lambda _path: snapshot)

    response = client.post("/api/v1/orchestrator/run")
    assert response.status_code == 200, response.text
    assert response.json()["started"] == []
    policy = response.json()["concurrency"]
    assert policy["adaptive_enabled"] is True
    assert policy["configured_max"] == 4
    assert policy["recommended_max"] == 1
    assert policy["effective_dispatch_budget"] == 1
    assert policy["applied_automatically"] is True


def test_overlapping_run_request_is_refused(client, monkeypatch):
    monkeypatch.setenv("AATM_EXECUTION_ENABLED", "1")
    lock = client.app.state.orchestrator_run_lock
    assert lock.acquire(blocking=False)
    try:
        response = client.post("/api/v1/orchestrator/run")
    finally:
        lock.release()
    assert response.status_code == 409
    assert "already active" in response.json()["detail"]


def test_status_reports_execution_as_disabled(client):
    body = client.get("/api/v1/orchestrator/status").json()
    assert body["executor"]["configured"] is False
    assert body["executor"]["name"] == "DisabledExecutor"
