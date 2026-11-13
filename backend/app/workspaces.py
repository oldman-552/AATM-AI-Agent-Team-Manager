"""Isolated Git worktree workspaces for projects.

Safety rules (all enforced here, not in the UI):

* A project workspace lives strictly under the configured root; the resolved
  path must not escape it (path traversal and symlink escapes are rejected).
* Branches are constrained to a safe charset and a per-project prefix.
* Network fetch/push and protected-branch merges are not implemented. A
  separate, explicit endpoint can fast-forward an independently approved task
  commit into a clean non-protected local branch under strict safety checks.
* Workspace deletion is explicit, audited, and root-guarded; task worktrees are
  not deleted by task integration. `protected_branches` is enforced by both
  branch creation and the task-integration gate.
* No credentials are read; Git subprocesses run with prompts disabled and a
  scrubbed environment so a remote URL could never block on a password prompt.
"""

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,120}$")
PROTECTED_BRANCHES = ("main", "master")


class WorkspaceError(RuntimeError):
    """A safe, user-facing workspace failure."""


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    project_dir: Path

    def as_dict(self) -> dict[str, str]:
        return {"root": str(self.root), "project_dir": str(self.project_dir)}


def _git_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "true",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
    }
    if os.name == "nt":
        for key in ("SYSTEMROOT", "TEMP", "TMP", "USERPROFILE"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def run_git(args: list[str], cwd: Path, *, timeout: int = 60) -> str:
    """Run a local git command without interactive prompts."""
    if not shutil.which("git"):
        raise WorkspaceError("Git is not installed or not on PATH.")
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkspaceError("Git command timed out.") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        message = detail[-1] if detail else "unknown git error"
        raise WorkspaceError(f"Git command failed: {message[:300]}")
    return completed.stdout.strip()


def run_git_bounded(
    args: list[str],
    cwd: Path,
    *,
    max_output_bytes: int = 256 * 1024,
    timeout: int = 15,
) -> tuple[str, bool]:
    """Run read-only Git output with a hard capture limit and timeout.

    The reader kills Git as soon as it observes output beyond the cap, rather
    than capturing an arbitrarily large diff and truncating it afterward.
    Returns decoded output and whether it was truncated.
    """
    if not shutil.which("git"):
        raise WorkspaceError("Git is not installed or not on PATH.")
    if max_output_bytes < 1:
        raise ValueError("max_output_bytes must be positive")
    try:
        process = subprocess.Popen(
            ["git", *args],
            cwd=str(cwd),
            env=_git_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        raise WorkspaceError("Could not start Git.") from exc

    captured = bytearray()
    truncated = threading.Event()

    def drain() -> None:
        assert process.stdout is not None
        while chunk := process.stdout.read(8192):
            remaining = max_output_bytes + 1 - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            if len(captured) > max_output_bytes:
                truncated.set()
                try:
                    process.kill()
                except OSError:
                    pass
                return

    reader = threading.Thread(target=drain, name="aatm-git-output", daemon=True)
    reader.start()
    try:
        process.wait(timeout=max(1, timeout))
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        reader.join(timeout=2)
        if process.stdout is not None:
            process.stdout.close()
        raise WorkspaceError("Git command timed out.") from exc
    reader.join(timeout=2)
    if reader.is_alive():
        process.kill()
        process.wait()
        raise WorkspaceError("Git output reader did not stop cleanly.")
    if process.stdout is not None:
        process.stdout.close()

    output = bytes(captured[:max_output_bytes])
    was_truncated = truncated.is_set() or len(captured) > max_output_bytes
    if process.returncode != 0 and not was_truncated:
        detail = output.decode("utf-8", errors="replace").strip().splitlines()
        message = detail[-1] if detail else "unknown git error"
        raise WorkspaceError(f"Git command failed: {message[:300]}")
    return output.decode("utf-8", errors="replace"), was_truncated


def validate_branch_name(branch: str) -> str:
    candidate = branch.strip()
    if not BRANCH_PATTERN.fullmatch(candidate):
        raise WorkspaceError(
            "Branch names may only contain letters, digits, '.', '_', '/' and '-'."
        )
    if (
        ".." in candidate
        or "//" in candidate
        or candidate.startswith("/")
        or candidate.endswith("/")
        or candidate.endswith(".")
        or candidate.endswith(".lock")
    ):
        raise WorkspaceError("Branch name contains an unsafe path sequence.")
    if candidate in PROTECTED_BRANCHES:
        raise WorkspaceError("Protected branches cannot be used as workspace branches.")
    return candidate


def workspace_paths(root: Path, project_id: str, slug: str) -> WorkspacePaths:
    """Resolve a project workspace directory and refuse to escape the root."""
    resolved_root = Path(root).expanduser().resolve()
    safe_slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-") or "project"
    safe_id = re.sub(r"[^a-zA-Z0-9-]", "", project_id)[:36]
    if not safe_id:
        raise WorkspaceError("Invalid project identifier.")
    candidate = (resolved_root / f"{safe_slug}-{safe_id}").resolve()
    if resolved_root not in candidate.parents and candidate != resolved_root:
        raise WorkspaceError("Workspace path escaped the configured root.")
    return WorkspacePaths(root=resolved_root, project_dir=candidate)


def stored_workspace_paths(root: str, workspace_path: str) -> WorkspacePaths:
    """Rebuild paths from persisted values without re-deriving the slug.

    Deriving the directory name from the project title again would break as
    soon as the project is renamed, so the persisted path is authoritative and
    is re-validated against the root before use.
    """
    resolved_root = Path(root).expanduser().resolve()
    candidate = Path(workspace_path).expanduser().resolve()
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise WorkspaceError("Stored workspace path is outside the configured root.")
    if not candidate.exists():
        raise WorkspaceError("Workspace directory is missing on disk.")
    return WorkspacePaths(root=resolved_root, project_dir=candidate)


def init_local_repository(path: Path) -> None:
    """Create a local git repository with an initial commit (test/bootstrap helper)."""
    path.mkdir(parents=True, exist_ok=True)
    run_git(["init", "--quiet", "-b", "main"], cwd=path)
    run_git(["config", "user.email", "aatm@localhost"], cwd=path)
    run_git(["config", "user.name", "AATM Local"], cwd=path)
    (path / "README.md").write_text("# Local project\n", encoding="utf-8")
    run_git(["add", "README.md"], cwd=path)
    run_git(["commit", "--quiet", "-m", "Initial local commit"], cwd=path)


def create_project_workspace(root: Path, project_id: str, slug: str, source: Path | None = None) -> WorkspacePaths:
    """Create an isolated workspace by cloning a *local* source (never a URL)."""
    paths = workspace_paths(root, project_id, slug)
    if paths.project_dir.exists():
        raise WorkspaceError("A workspace already exists for this project.")
    if source is not None:
        source_path = Path(source).expanduser().resolve()
        if not (source_path / ".git").exists():
            raise WorkspaceError("The workspace source must be an existing local Git repository.")
        paths.root.mkdir(parents=True, exist_ok=True)
        run_git(["clone", "--quiet", str(source_path), str(paths.project_dir)], cwd=paths.root)
    else:
        init_local_repository(paths.project_dir)
    return paths


def create_work_branch(paths: WorkspacePaths, branch: str) -> str:
    """Create and check out a fresh work branch in the workspace."""
    name = validate_branch_name(branch)
    if not (paths.project_dir / ".git").exists():
        raise WorkspaceError("The project workspace is not an initialized Git repository.")
    run_git(["checkout", "--quiet", "-b", name], cwd=paths.project_dir)
    return name


def workspace_status(paths: WorkspacePaths) -> dict[str, object]:
    """Read-only workspace report. Never mutates the repository."""
    if not (paths.project_dir / ".git").exists():
        raise WorkspaceError("The project workspace is not an initialized Git repository.")
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=paths.project_dir)
    porcelain = run_git(["status", "--porcelain"], cwd=paths.project_dir)
    changed = [line for line in porcelain.splitlines() if line.strip()]
    try:
        diffstat = run_git(["diff", "--stat", "--no-color"], cwd=paths.project_dir)
    except WorkspaceError:
        diffstat = ""
    head = run_git(["rev-parse", "HEAD"], cwd=paths.project_dir)
    return {
        "branch": branch,
        "head_commit": head,
        "on_protected_branch": branch in PROTECTED_BRANCHES,
        "clean": not changed,
        "changed_files": [line[3:] for line in changed][:200],
        "changed_count": len(changed),
        "diffstat": diffstat,
        "note": "Read-only status; this endpoint never merges, pushes or deletes workspace content.",
    }


def remove_workspace(paths: WorkspacePaths) -> None:
    """Delete a workspace directory — requires explicit caller intent and a safe path."""
    resolved = paths.project_dir.resolve()
    if resolved == paths.root.resolve() or paths.root.resolve() not in resolved.parents:
        raise WorkspaceError("Refusing to delete a path outside the workspace root.")
    if not resolved.exists():
        return
    shutil.rmtree(resolved)
