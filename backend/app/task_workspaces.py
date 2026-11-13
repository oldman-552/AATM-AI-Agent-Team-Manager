"""Per-task Git worktrees for safe concurrent execution in one project.

The orchestrator creates worktrees serially on its control thread before it
starts executor threads. Each task gets a deterministic directory below the
configured workspace root; a small owner record prevents reuse of a directory
that was not created by AATM for that exact task.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from app.workspaces import WorkspaceError, WorkspacePaths, run_git, run_git_bounded, workspace_status

WORKTREE_ROOT_NAME = ".aatm-task-worktrees"
TASK_DIFF_PREVIEW_BYTES = 256 * 1024
_UNTRACKED_LIST_BYTES = 64 * 1024
_UNTRACKED_FILE_BYTES = 32 * 1024
_UNTRACKED_TOTAL_BYTES = 128 * 1024
_MAX_UNTRACKED_FILES = 32
_SAFE_ID = re.compile(r"^[A-Za-z0-9-]{1,80}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _validate_ids(project_id: str, task_id: str) -> None:
    if not _SAFE_ID.fullmatch(project_id) or not _SAFE_ID.fullmatch(task_id):
        raise WorkspaceError("Project or task identifier is not safe for a task worktree path.")


def _paths(root: str | Path, source: str | Path, project_id: str, task_id: str) -> tuple[Path, Path, Path]:
    _validate_ids(project_id, task_id)
    resolved_root = Path(root).expanduser().resolve()
    resolved_source = Path(source).expanduser().resolve()
    if resolved_source == resolved_root or resolved_root not in resolved_source.parents:
        raise WorkspaceError("Project workspace is outside the configured root; refusing to create a task worktree.")
    parent = (resolved_root / WORKTREE_ROOT_NAME / project_id).resolve()
    if resolved_root not in parent.parents:
        raise WorkspaceError("Task worktree path escaped the configured workspace root.")
    target = parent / task_id
    owner_file = parent / f"{task_id}.owner.json"
    if target == resolved_source or target in resolved_source.parents or resolved_source in target.parents:
        raise WorkspaceError("Task worktree path overlaps the registered project workspace.")
    return resolved_root, target, owner_file


def is_git_workspace(root: str | Path, source: str | Path, project_id: str, task_id: str) -> bool:
    """Return true only for a valid, root-contained Git workspace."""
    _root, _target, _owner_file = _paths(root, source, project_id, task_id)
    source_path = Path(source).expanduser().resolve()
    if not (source_path / ".git").exists():
        return False
    try:
        top_level = Path(run_git(["rev-parse", "--show-toplevel"], cwd=source_path)).resolve()
    except WorkspaceError:
        return False
    return top_level == source_path


def existing_task_worktree(
    root: str | Path,
    source: str | Path,
    project_id: str,
    task_id: str,
) -> Path | None:
    """Validate and return an existing registered task worktree, if present."""
    _root, target, owner_file = _paths(root, source, project_id, task_id)
    if not owner_file.exists() and not target.exists():
        return None
    if owner_file.is_symlink() or target.is_symlink() or not owner_file.is_file() or not target.is_dir():
        raise WorkspaceError("Task worktree metadata is incomplete or symlinked; refusing to guess or overwrite files.")
    resolved_root = Path(root).expanduser().resolve()
    resolved_target = target.resolve()
    if resolved_target == resolved_root or resolved_root not in resolved_target.parents:
        raise WorkspaceError("Task worktree resolves outside the configured root.")
    try:
        owner = json.loads(owner_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError("Task worktree ownership record is unreadable.") from exc
    if not isinstance(owner, dict):
        raise WorkspaceError("Task worktree ownership record has an invalid format.")
    expected = {
        "project_id": project_id,
        "task_id": task_id,
        "source_path": str(Path(source).expanduser().resolve()),
    }
    if any(owner.get(key) != value for key, value in expected.items()):
        raise WorkspaceError("Task worktree ownership record does not match this task.")
    try:
        top_level = Path(run_git(["rev-parse", "--show-toplevel"], cwd=target)).resolve()
    except WorkspaceError as exc:
        raise WorkspaceError("Registered task worktree is not a usable Git worktree.") from exc
    if top_level != target.resolve():
        raise WorkspaceError("Registered task worktree resolves to a different directory.")
    return target


def prepare_task_worktree(
    root: str | Path,
    source: str | Path,
    project_id: str,
    task_id: str,
) -> Path | None:
    """Create or reuse a task worktree; returns None for non-Git test workspaces.

    Git metadata writes happen in the serial orchestrator preparation phase,
    never in executor worker threads. The returned worktree remains available
    after success/failure for operator inspection and task retry.
    """
    resolved_root, target, owner_file = _paths(root, source, project_id, task_id)
    source_path = Path(source).expanduser().resolve()
    if not is_git_workspace(resolved_root, source_path, project_id, task_id):
        return None
    existing = existing_task_worktree(resolved_root, source_path, project_id, task_id)
    if existing is not None:
        return existing
    if target.exists() or owner_file.exists():
        raise WorkspaceError("Unregistered task worktree path already exists; refusing to reuse it.")

    base_commit = run_git(["rev-parse", "HEAD"], cwd=source_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    run_git(["worktree", "add", "--quiet", "--detach", str(target), base_commit], cwd=source_path)
    owner = {
        "project_id": project_id,
        "task_id": task_id,
        "source_path": str(source_path),
        "base_commit": base_commit,
    }
    temporary = owner_file.with_name(owner_file.name + f".{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(owner, sort_keys=True), encoding="utf-8")
        os.replace(temporary, owner_file)
    except OSError as exc:
        try:
            run_git(["worktree", "remove", "--force", str(target)], cwd=source_path)
        except WorkspaceError:
            pass
        temporary.unlink(missing_ok=True)
        raise WorkspaceError("Could not persist task worktree ownership metadata.") from exc
    return target


def inspect_task_worktree(
    root: str | Path,
    source: str | Path,
    project_id: str,
    task_id: str,
) -> dict[str, object] | None:
    """Return read-only status metadata without exposing file contents."""
    target = existing_task_worktree(root, source, project_id, task_id)
    if target is None:
        return None
    _root, _target, owner_file = _paths(root, source, project_id, task_id)
    try:
        owner = json.loads(owner_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError("Task worktree ownership record is unreadable.") from exc
    base_commit = owner.get("base_commit") if isinstance(owner, dict) else None
    if not isinstance(base_commit, str) or not _COMMIT.fullmatch(base_commit):
        raise WorkspaceError("Task worktree base commit metadata is invalid.")
    status = workspace_status(WorkspacePaths(root=Path(root).expanduser().resolve(), project_dir=target.resolve()))
    return {
        "task_id": task_id,
        "worktree_path": str(target),
        "base_commit": base_commit,
        **status,
        "content_included": False,
        "note": "Read-only metadata only; file contents are not exposed and AATM does not merge or delete task worktrees.",
    }


def _untracked_previews(worktree: Path) -> tuple[list[dict[str, object]], bool]:
    """Capture small UTF-8 text previews for safe untracked regular files."""
    listing, listing_truncated = run_git_bounded(
        ["ls-files", "--others", "--exclude-standard", "-z"],
        cwd=worktree,
        max_output_bytes=_UNTRACKED_LIST_BYTES,
        timeout=5,
    )
    names = [name for name in listing.split("\0") if name]
    previews: list[dict[str, object]] = []
    total_content_bytes = 0
    was_truncated = listing_truncated or len(names) > _MAX_UNTRACKED_FILES
    root = worktree.resolve()

    for name in names[:_MAX_UNTRACKED_FILES]:
        entry: dict[str, object] = {
            "path": name,
            "size_bytes": None,
            "content": None,
            "status": "unsafe",
            "truncated": False,
        }
        if "\ufffd" in name or Path(name).is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")):
            previews.append(entry)
            continue
        candidate = worktree
        symlinked = False
        for part in name.split("/"):
            candidate = candidate / part
            if candidate.is_symlink():
                symlinked = True
                break
        if symlinked:
            entry["status"] = "symlink"
            previews.append(entry)
            continue
        try:
            resolved = candidate.resolve(strict=True)
            if resolved == root or root not in resolved.parents:
                previews.append(entry)
                continue
            metadata = candidate.stat(follow_symlinks=False)
            entry["size_bytes"] = metadata.st_size
            if not stat.S_ISREG(metadata.st_mode):
                entry["status"] = "non_regular"
                previews.append(entry)
                continue
            if metadata.st_size > _UNTRACKED_FILE_BYTES:
                entry["status"] = "too_large"
                entry["truncated"] = True
                was_truncated = True
                previews.append(entry)
                continue
            with candidate.open("rb") as stream:
                content = stream.read(_UNTRACKED_FILE_BYTES + 1)
        except OSError:
            entry["status"] = "unreadable"
            previews.append(entry)
            continue

        if b"\0" in content:
            entry["status"] = "binary"
            previews.append(entry)
            continue
        if len(content) > _UNTRACKED_FILE_BYTES:
            entry["status"] = "too_large"
            entry["truncated"] = True
            was_truncated = True
            previews.append(entry)
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            entry["status"] = "binary"
            previews.append(entry)
            continue
        budget = _UNTRACKED_TOTAL_BYTES - total_content_bytes
        encoded = text.encode("utf-8")
        if budget <= 0:
            entry["status"] = "omitted_limit"
            entry["truncated"] = True
            was_truncated = True
        else:
            if len(encoded) > budget:
                text = encoded[:budget].decode("utf-8", errors="ignore")
                entry["truncated"] = True
                was_truncated = True
            entry["status"] = "text"
            entry["content"] = text
            total_content_bytes += len(text.encode("utf-8"))
        previews.append(entry)

    return previews, was_truncated


def preview_task_worktree_diff(
    root: str | Path,
    source: str | Path,
    project_id: str,
    task_id: str,
) -> dict[str, object] | None:
    """Return a capped text diff from the owned worktree's original base commit.

    Untracked files are intentionally omitted from patch text. Their names
    remain visible through `inspect_task_worktree`; no external diff or
    textconv command is allowed to run.
    """
    target = existing_task_worktree(root, source, project_id, task_id)
    if target is None:
        return None
    _root, _target, owner_file = _paths(root, source, project_id, task_id)
    try:
        owner = json.loads(owner_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError("Task worktree ownership record is unreadable.") from exc
    base_commit = owner.get("base_commit") if isinstance(owner, dict) else None
    if not isinstance(base_commit, str) or not _COMMIT.fullmatch(base_commit):
        raise WorkspaceError("Task worktree base commit metadata is invalid.")
    head_commit = run_git(["rev-parse", "HEAD"], cwd=target)
    try:
        run_git(["merge-base", "--is-ancestor", base_commit, head_commit], cwd=target)
    except WorkspaceError as exc:
        raise WorkspaceError("Task worktree base commit is not an ancestor of its current HEAD.") from exc
    diff, truncated = run_git_bounded(
        [
            "-c", "core.fsmonitor=false",
            "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--no-renames", "--unified=3",
            base_commit, "--",
        ],
        cwd=target,
        max_output_bytes=TASK_DIFF_PREVIEW_BYTES,
    )
    # Ensure UTF-8 replacement decoding cannot expand invalid bytes past the
    # public response cap.
    encoded = diff.encode("utf-8")
    if len(encoded) > TASK_DIFF_PREVIEW_BYTES:
        diff = encoded[:TASK_DIFF_PREVIEW_BYTES].decode("utf-8", errors="ignore")
        truncated = True
    untracked_files, untracked_truncated = _untracked_previews(target)
    return {
        "task_id": task_id,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "diff": diff,
        "truncated": truncated,
        "max_bytes": TASK_DIFF_PREVIEW_BYTES,
        "untracked_files": untracked_files,
        "untracked_included": any(item["status"] == "text" for item in untracked_files),
        "untracked_truncated": untracked_truncated,
        "untracked_max_bytes": _UNTRACKED_TOTAL_BYTES,
        "note": "Read-only text preview only. Untracked regular UTF-8 files may be included within separate strict limits; binary, unsafe, and oversized output is omitted or truncated.",
    }
