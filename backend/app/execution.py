"""A real, bounded local executor for the orchestrator boundary.

`DisabledExecutor` refuses to run, which is the right default. This module adds
the first executor that *actually* does work — a bounded subprocess runner — with
the safety properties spelled out per rule below.

The central design decision is **where the command comes from**. Executing a
command string taken from the database would turn every task title into remote
code execution, so this deliberately does not do that:

* A task only names a command, via an acceptance criterion of the form
  ``run:<name>``.
* The argv for that name lives in ``.aatm/exec.json`` inside the project's
  isolated workspace, under operator control and versioned with the repo.
* The program must be on an allow-list, is invoked without a shell, and is
  resolved through ``PATH`` rather than from a relative path.

So the worst a hostile task can do is name a command that already exists in a
file a human committed.

Safety rules, each covered by a test:

1. **No shell.** argv lists only; no globbing, pipes or redirection.
2. **Allow-listed programs.** ``argv[0]`` must be a bare name on the list; a
   path such as ``./evil`` or ``/bin/sh`` is rejected outright.
3. **Contained working directory.** The resolved cwd must be inside the
   registered workspace, so ``..`` cannot escape it.
4. **Sanitised environment.** The child gets ``PATH`` and ``LANG`` only. Provider
   keys and ``AATM_*`` variables are never inherited.
5. **Bounded runtime and output.** A wall-clock timeout and an output cap; both
   terminate the process group, not just the direct child.
6. **Cooperative cancellation.** While the process runs, cancellation intent is
   polled from the database; a cancelled task's process is terminated and the
   orchestrator records a cancellation rather than a failure.
7. **Graceful shutdown.** Every live process is registered so an application
   shutdown can terminate them instead of leaving orphans.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.models import ProjectWorkspace, Task
from app.orchestrator import ExecutionCancelled, ExecutionLeaseLost, ExecutionOutcomeError, ExecutionResult
from app.task_workspaces import existing_task_worktree, is_git_workspace, prepare_task_worktree
from app.workspaces import WorkspaceError

COMMANDS_DIR = ".aatm"
COMMANDS_FILE = "exec.json"

MAX_COMMAND_TIMEOUT = 900
DEFAULT_TIMEOUT = 60
MAX_OUTPUT_BYTES = 64 * 1024
MAX_ARGV_LENGTH = 64
MAX_ARG_LENGTH = 4096
DEFAULT_ALLOWED_PROGRAMS = (
    "python3",
    "python",
    "node",
    "npm",
    "pytest",
    "echo",
    "printf",
    "true",
    "false",
)
# The only variables a child process inherits.
PASSTHROUGH_ENV = ("PATH", "LANG", "LC_ALL", "TZ")


class ExecutionError(ValueError):
    """A safe, user-facing execution refusal (never a traceback)."""


@dataclass(frozen=True)
class CommandSpec:
    """One named command from a workspace's ``exec.json``."""

    name: str
    argv: tuple[str, ...]
    timeout_seconds: int = DEFAULT_TIMEOUT

    def __post_init__(self) -> None:
        if not self.argv:
            raise ExecutionError(f"Command '{self.name}' has an empty argv.")
        if len(self.argv) > MAX_ARGV_LENGTH:
            raise ExecutionError(
                f"Command '{self.name}' has {len(self.argv)} arguments; the limit is {MAX_ARGV_LENGTH}."
            )
        for arg in self.argv:
            if len(arg) > MAX_ARG_LENGTH:
                raise ExecutionError(f"Command '{self.name}' has an argument longer than {MAX_ARG_LENGTH} characters.")
        if not (1 <= self.timeout_seconds <= MAX_COMMAND_TIMEOUT):
            raise ExecutionError(
                f"Command '{self.name}' requests a {self.timeout_seconds}s timeout; allowed range is 1-{MAX_COMMAND_TIMEOUT}."
            )


@dataclass
class ExecutionRecord:
    """What actually happened, for the audit trail. No invented fields."""

    command: str
    argv: tuple[str, ...]
    exit_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False
    output_truncated: bool = False
    overflowed: bool = False
    cancelled: bool = False
    lease_lost: bool = False
    cwd: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "duration_seconds": round(self.duration_seconds, 3),
            "timed_out": self.timed_out,
            "output_truncated": self.output_truncated,
            "cancelled": self.cancelled,
            "lease_lost": self.lease_lost,
            "cwd": self.cwd,
        }


@dataclass
class _LiveProcess:
    process: subprocess.Popen
    started: float
    record: ExecutionRecord
    cancelled: bool = False
    timed_out: bool = False


# Registered so shutdown can terminate everything still running.
_ACTIVE: dict[int, _LiveProcess] = {}
_ACTIVE_LOCK = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def command_name_for(task: Task) -> str:
    """The command this task requests, from ``run:<name>`` acceptance criteria.

    Exactly one is allowed: two ``run:`` criteria would make the outcome depend
    on listing order, which is not something an operator should have to reason
    about.
    """
    names: list[str] = []
    for criterion in task.acceptance_criteria or []:
        text = str(criterion).strip()
        if text.lower().startswith("run:"):
            names.append(text[4:].strip())
    if not names:
        raise ExecutionError(
            "This task names no command. Add an acceptance criterion of the form 'run:<name>' "
            f"and define that name in {COMMANDS_DIR}/{COMMANDS_FILE}."
        )
    if len(names) > 1:
        raise ExecutionError(
            f"Task names {len(names)} commands ({', '.join(names)}); exactly one 'run:<name>' criterion is allowed."
        )
    if not names[0]:
        raise ExecutionError("The 'run:' criterion has no command name after it.")
    return names[0]


def load_commands(project_dir: Path) -> dict[str, CommandSpec]:
    """Read ``.aatm/exec.json``. A missing file is an error, not an empty set."""
    path = project_dir / COMMANDS_DIR / COMMANDS_FILE
    if not path.is_file():
        raise ExecutionError(f"No command file at {COMMANDS_DIR}/{COMMANDS_FILE} in the project workspace.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExecutionError(f"{COMMANDS_DIR}/{COMMANDS_FILE} is not valid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ExecutionError(f"{COMMANDS_DIR}/{COMMANDS_FILE} must contain an object mapping names to commands.")
    commands: dict[str, CommandSpec] = {}
    for name, value in raw.items():
        if not isinstance(value, dict):
            raise ExecutionError(f"Command '{name}' must be an object with 'argv' and optional 'timeout_seconds'.")
        argv = value.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            raise ExecutionError(f"Command '{name}' needs 'argv' as a list of strings.")
        timeout = value.get("timeout_seconds", DEFAULT_TIMEOUT)
        if not isinstance(timeout, int):
            raise ExecutionError(f"Command '{name}' has a non-integer 'timeout_seconds'.")
        commands[name] = CommandSpec(name=name, argv=tuple(argv), timeout_seconds=timeout)
    return commands


class LocalProcessExecutor:
    """Runs one named, allow-listed command per task inside its workspace."""

    def __init__(
        self,
        session_factory,
        *,
        allowed_programs: tuple[str, ...] = DEFAULT_ALLOWED_PROGRAMS,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        cancel_poll_seconds: float = 0.2,
    ) -> None:
        self.session_factory = session_factory
        self.allowed_programs = tuple(allowed_programs)
        self.max_output_bytes = max(1024, max_output_bytes)
        self.cancel_poll_seconds = max(0.05, cancel_poll_seconds)

    # -- task isolation -------------------------------------------------
    def _workspace_context(self, task: Task) -> tuple[str, Path] | None:
        if not task.project_id:
            return None
        with self.session_factory() as session:
            workspace = session.scalar(
                select(ProjectWorkspace).where(ProjectWorkspace.project_id == task.project_id)
            )
            if workspace is None:
                return None
            return workspace.root_path, Path(workspace.workspace_path).expanduser().resolve()

    def dispatch_group(self, task: Task) -> str:
        """Share a dispatch slot only when tasks lack independent Git worktrees."""
        context = self._workspace_context(task)
        if context is None:
            return f"task:{task.id}"
        root, project_dir = context
        try:
            if is_git_workspace(root, project_dir, task.project_id or "", task.id):
                return f"task:{task.id}"
        except WorkspaceError:
            pass
        return f"project:{task.project_id}"

    def prepare_task(self, task: Task) -> None:
        """Prepare isolated Git files on the orchestrator thread before dispatch."""
        context = self._workspace_context(task)
        if context is None:
            return
        root, project_dir = context
        try:
            prepare_task_worktree(root, project_dir, task.project_id or "", task.id)
        except WorkspaceError as exc:
            raise ExecutionOutcomeError(f"Could not prepare an isolated task workspace: {exc}") from exc

    # -- resolution -----------------------------------------------------
    def resolve(self, task: Task) -> tuple[CommandSpec, Path]:
        name = command_name_for(task)
        with self.session_factory() as session:
            workspace = session.scalar(
                select(ProjectWorkspace).where(ProjectWorkspace.project_id == task.project_id)
            )
            if workspace is None:
                raise ExecutionError(
                    "This project has no workspace, so there is nowhere to run a command. "
                    "Create one first; the executor never falls back to the application directory."
                )
            project_dir = Path(workspace.workspace_path).expanduser().resolve()
            root = Path(workspace.root_path).expanduser().resolve()
        try:
            task_project_dir = existing_task_worktree(root, project_dir, task.project_id or "", task.id)
        except WorkspaceError as exc:
            raise ExecutionError(f"The task's isolated workspace is invalid: {exc}") from exc
        if task_project_dir is not None:
            project_dir = task_project_dir.resolve()
        if not project_dir.is_dir():
            raise ExecutionError("The project workspace directory no longer exists on disk.")
        if project_dir != root and root not in project_dir.parents:
            raise ExecutionError("The project workspace resolves outside the configured root; refusing to run.")

        commands = load_commands(project_dir)
        spec = commands.get(name)
        if spec is None:
            raise ExecutionError(
                f"No command named '{name}' in {COMMANDS_DIR}/{COMMANDS_FILE}. "
                f"Available: {', '.join(sorted(commands)) or 'none'}."
            )
        program = spec.argv[0]
        if "/" in program or "\\" in program:
            raise ExecutionError(
                f"Command '{name}' uses a path ('{program}'). Only bare program names are allowed; "
                "a relative path could point at any file in the workspace."
            )
        if program not in self.allowed_programs:
            raise ExecutionError(
                f"Program '{program}' is not allow-listed. Allowed: {', '.join(self.allowed_programs)}."
            )
        if shutil.which(program) is None:
            raise ExecutionError(f"Program '{program}' is not installed or not on PATH.")
        return spec, project_dir

    # -- execution ------------------------------------------------------
    def __call__(self, task: Task) -> ExecutionResult:
        spec, cwd = self.resolve(task)
        record = self._run(task, spec, cwd)
        if record.lease_lost:
            raise ExecutionLeaseLost(f"Task '{task.title}' lost its lease while running '{spec.name}'.")
        if record.cancelled:
            raise ExecutionCancelled(f"Task '{task.title}' was cancelled while running '{spec.name}'.")
        evidence = self._evidence(record)
        if record.timed_out:
            raise ExecutionOutcomeError(
                f"Command '{spec.name}' exceeded its {spec.timeout_seconds}s timeout and was terminated. {evidence}"
            )
        if record.exit_code != 0:
            raise ExecutionOutcomeError(
                f"Command '{spec.name}' exited with status {record.exit_code}. {evidence}"
            )
        return ExecutionResult(output=record.stdout or "(no output)", evidence=evidence)

    def _run(self, task: Task, spec: CommandSpec, cwd: Path) -> ExecutionRecord:
        env = {key: os.environ[key] for key in PASSTHROUGH_ENV if key in os.environ}
        env.setdefault("PATH", os.defpath)
        started = time.monotonic()
        record = ExecutionRecord(
            command=spec.name,
            argv=spec.argv,
            exit_code=None,
            duration_seconds=0.0,
            stdout="",
            stderr="",
            cwd=str(cwd),
        )
        # start_new_session puts the child in its own process group so a timeout
        # can kill grandchildren too; killing only the direct child leaks workers.
        process = subprocess.Popen(  # noqa: S603 - argv list, no shell, allow-listed program
            list(spec.argv),
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=False,
        )
        # Drain both pipes from the moment the process starts. Waiting first and
        # calling communicate() afterwards deadlocks: a child that writes more
        # than the OS pipe buffer (~64 KB) blocks on write and never exits.
        stdout_buf, stderr_buf = bytearray(), bytearray()
        stdout_overflow, stderr_overflow = [False], [False]
        drainers = [
            threading.Thread(
                target=_drain, args=(process.stdout, stdout_buf, self.max_output_bytes, stdout_overflow), daemon=True
            ),
            threading.Thread(
                target=_drain, args=(process.stderr, stderr_buf, self.max_output_bytes, stderr_overflow), daemon=True
            ),
        ]
        for drainer in drainers:
            drainer.start()

        live = _LiveProcess(process=process, started=started, record=record)
        with _ACTIVE_LOCK:
            _ACTIVE[process.pid] = live
        try:
            killed_by = self._supervise(task, live, spec.timeout_seconds)
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE.pop(process.pid, None)
        for drainer in drainers:
            drainer.join(timeout=5)
        stdout, stderr = bytes(stdout_buf), bytes(stderr_buf)
        record.overflowed = stdout_overflow[0] or stderr_overflow[0]
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        record.duration_seconds = time.monotonic() - started
        record.exit_code = process.returncode
        decoded_out, truncated_out = _decode(stdout, self.max_output_bytes)
        decoded_err, truncated_err = _decode(stderr, self.max_output_bytes)
        record.stdout, record.stderr = decoded_out, decoded_err
        record.output_truncated = truncated_out or truncated_err or record.overflowed
        record.timed_out = killed_by == "timeout"
        record.cancelled = killed_by == "cancelled"
        record.lease_lost = killed_by == "lease_lost"
        return record

    def _supervise(self, task: Task, live: _LiveProcess, timeout_seconds: int) -> str | None:
        """Wait for the process, polling for timeout and cancellation intent.

        Returns why it was terminated, or None if it exited on its own.
        """
        # `started` is time.monotonic(); mixing in a wall clock makes the
        # comparison meaningless and kills every process immediately.
        deadline = live.started + timeout_seconds
        killed_by: str | None = None
        while True:
            if live.process.poll() is not None:
                break
            if time.monotonic() >= deadline:
                killed_by = "timeout"
                self._terminate(live)
                break
            stop_reason = self._stop_reason(task)
            if stop_reason is not None:
                killed_by = stop_reason
                self._terminate(live)
                break
            time.sleep(self.cancel_poll_seconds)
        try:
            live.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Terminated but still not reaped: stop waiting, the caller records
            # the timeout either way rather than blocking the orchestrator.
            pass
        return killed_by

    @staticmethod
    def _terminate(live: _LiveProcess) -> None:
        """Ask the whole process group to stop, then insist."""
        try:
            os.killpg(os.getpgid(live.process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        try:
            live.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(live.process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _stop_reason(self, task: Task) -> str | None:
        """Read cancellation and lease ownership fresh while a process runs."""
        try:
            with self.session_factory() as session:
                row = session.execute(
                    select(
                        Task.cancel_requested_at,
                        Task.state,
                        Task.lease_owner,
                        Task.lease_expires_at,
                    ).where(Task.id == task.id)
                ).one_or_none()
        except Exception:
            # For an orchestrated task, an unverifiable lease is unsafe to keep
            # executing. Direct executor use without a lease remains supported.
            return "lease_lost" if task.state == "running" else None
        if row is None:
            return "lease_lost" if task.state == "running" else None
        requested, state, owner, expires_at = row
        if requested is not None:
            return "cancelled"
        if task.state == "running":
            expected_owner = task.lease_owner
            current_expiry = expires_at if expires_at and expires_at.tzinfo else (
                expires_at.replace(tzinfo=timezone.utc) if expires_at else None
            )
            if (
                state != "running"
                or not expected_owner
                or owner != expected_owner
                or current_expiry is None
                or current_expiry <= _utc_now()
            ):
                return "lease_lost"
        return None

    def _evidence(self, record: ExecutionRecord) -> str:
        parts = [
            f"Ran '{record.command}' ({' '.join(record.argv)}).",
            f"Exit status {record.exit_code} after {record.duration_seconds:.2f}s.",
            f"Execution workspace: {record.cwd}.",
        ]
        if record.output_truncated:
            parts.append(f"Output truncated at {self.max_output_bytes} bytes.")
        if record.stderr:
            tail = record.stderr.strip().splitlines()[-3:]
            parts.append("stderr: " + " | ".join(tail))
        return " ".join(parts)[:2000]

    def shutdown(self, timeout_seconds: int = 10) -> int:
        """Terminate every live process. Returns how many were stopped."""
        with _ACTIVE_LOCK:
            live = list(_ACTIVE.values())
        for entry in live:
            self._terminate(entry)
        deadline = time.monotonic() + timeout_seconds
        for entry in live:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                entry.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pass
        return len(live)


def _drain(stream, buffer: bytearray, limit: int, overflow: list[bool]) -> None:
    """Read a pipe to EOF, keeping at most ``limit`` bytes.

    Reading continues past the limit deliberately: stopping would block the
    child on write, which is the deadlock this whole helper exists to avoid.
    ``overflow`` records that data was dropped, so the evidence can say so
    instead of implying the output was complete.
    """
    if stream is None:
        return
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            if len(buffer) < limit:
                buffer.extend(chunk[: limit - len(buffer)])
            if len(buffer) >= limit:
                overflow[0] = True
    except (ValueError, OSError):
        return


def _decode(payload: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(payload) > limit
    text = payload[:limit].decode("utf-8", errors="replace")
    return text, truncated


# -- opt-in activation -----------------------------------------------------

EXECUTION_FLAG = "AATM_EXECUTION_ENABLED"
ALLOWED_PROGRAMS_FLAG = "AATM_EXECUTION_PROGRAMS"


def execution_enabled() -> bool:
    """Execution is off unless an operator opts in explicitly.

    The default must stay off: a local subprocess runner is a capability, and
    capabilities that turn themselves on are how accidents happen. Accepts
    "1"/"true"/"yes" so a shell export is not a trap.
    """
    return (os.environ.get(EXECUTION_FLAG) or "").strip().lower() in {"1", "true", "yes", "on"}


def configured_programs() -> tuple[str, ...]:
    """The allow-list, optionally narrowed by environment.

    An operator can restrict the defaults further, but cannot widen them past
    the built-in list — an environment variable is not a code-review boundary.
    """
    raw = (os.environ.get(ALLOWED_PROGRAMS_FLAG) or "").strip()
    if not raw:
        return DEFAULT_ALLOWED_PROGRAMS
    requested = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not requested:
        return DEFAULT_ALLOWED_PROGRAMS
    allowed = tuple(item for item in requested if item in DEFAULT_ALLOWED_PROGRAMS)
    return allowed or DEFAULT_ALLOWED_PROGRAMS


def shutdown_live_processes(timeout_seconds: int = 10) -> int:
    """Terminate every registered process group. Used by application shutdown.

    Module-level so it works without an executor instance: by the time the app is
    stopping, the executor that started the process may already be gone.
    """
    with _ACTIVE_LOCK:
        live = list(_ACTIVE.values())
    for entry in live:
        LocalProcessExecutor._terminate(entry)
    deadline = time.monotonic() + timeout_seconds
    for entry in live:
        try:
            entry.process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    return len(live)
