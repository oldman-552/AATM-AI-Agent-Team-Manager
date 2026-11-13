"""Approval-gated GitHub pull-request planning (no network, ever).

What this module really does
----------------------------

It records *intent*: a project's branch pair, a repository, a title and a body,
plus the approval request that must be granted before anything could happen.
It then computes the exact commands a future executor would run and keeps them
as an inert plan.

What it deliberately does **not** do
------------------------------------

* No `git push`, no `gh` invocation, no HTTP request to GitHub.
* No token reading. A future executor must take a token reference from `env:`
  or the OS keyring *server-side*; nothing here reads `GITHUB_TOKEN`.
* No claim of completion. `executed` is always `false`, and the execute endpoint
  refuses with an explicit reason rather than pretending.

This is the honest, useful half of the feature: the reviewable plan, the gate,
and the validation — without an unauthorized external write.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import add_event
from app.models import ApprovalRequest, GithubPullRequest, Project
from app.quality import ReviewError, decide_approval, request_approval

OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
BASE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,120}$")

EXECUTION_AVAILABLE = False
EXECUTION_REASON = (
    "Live GitHub execution is not implemented in this build: it requires a token supplied out of band "
    "(env:/keyring, never over HTTP) and an explicit human decision. No network request was made and "
    "nothing was pushed."
)


class GithubError(ValueError):
    """A safe, user-facing GitHub plan validation failure."""


def validate_owner(owner: str) -> str:
    candidate = (owner or "").strip()
    if not OWNER_PATTERN.fullmatch(candidate) or candidate.endswith("-"):
        raise GithubError("A GitHub owner must be 1–39 letters, digits or dashes and cannot end with a dash.")
    return candidate


def validate_repo(repo: str) -> str:
    candidate = (repo or "").strip()
    if not REPO_PATTERN.fullmatch(candidate) or candidate in {".", ".."}:
        raise GithubError("A repository name may only contain letters, digits, '.', '_' and '-' (max 100).")
    return candidate


def validate_base_branch(branch: str) -> str:
    candidate = (branch or "").strip()
    if (
        not BASE_PATTERN.fullmatch(candidate)
        or ".." in candidate
        or "//" in candidate
        or candidate.startswith("/")
        or candidate.endswith("/")
        or candidate.endswith(".")
        or candidate.endswith(".lock")
    ):
        raise GithubError("The base branch name is not a safe branch name.")
    return candidate


def build_plan_commands(owner: str, repo: str, base: str, head: str, title: str) -> list[str]:
    """The commands a future executor would run. Inert text — never executed here."""
    return [
        f"git push --set-upstream origin {head}",
        f"gh pr create --repo {owner}/{repo} --base {base} --head {head} "
        f'--title "{title}" --body-file -',
    ]


def create_plan(
    db: Session,
    project: Project,
    *,
    owner: str,
    repo: str,
    base_branch: str,
    head_branch: str,
    title: str,
    body: str = "",
    requested_by: str = "local-user",
) -> tuple[GithubPullRequest, ApprovalRequest]:
    """Record a pull-request plan and the approval that gates it."""
    clean_owner = validate_owner(owner)
    clean_repo = validate_repo(repo)
    clean_base = validate_base_branch(base_branch)
    clean_head = validate_base_branch(head_branch)
    if clean_head == clean_base:
        raise GithubError("The head branch must differ from the base branch.")
    clean_title = (title or "").strip()
    if not 1 <= len(clean_title) <= 200:
        raise GithubError("A pull request title of 1–200 characters is required.")
    if len(body or "") > 20_000:
        raise GithubError("A pull request body may be at most 20,000 characters.")

    duplicate = db.scalar(
        select(GithubPullRequest).where(
            GithubPullRequest.project_id == project.id,
            GithubPullRequest.owner == clean_owner,
            GithubPullRequest.repo == clean_repo,
            GithubPullRequest.head_branch == clean_head,
            GithubPullRequest.status.in_(("awaiting_approval", "approved_not_executed")),
        )
    )
    if duplicate is not None:
        raise GithubError("An open plan already exists for this repository and head branch.")

    approval = request_approval(
        db,
        kind="pull_request",
        entity_type="project",
        entity_id=project.id,
        summary=f"Open pull request {clean_owner}/{clean_repo}: {clean_head} → {clean_base}",
        requested_by=requested_by,
    )
    plan = GithubPullRequest(
        project_id=project.id,
        owner=clean_owner,
        repo=clean_repo,
        base_branch=clean_base,
        head_branch=clean_head,
        title=clean_title,
        body=(body or "").strip(),
        approval_id=approval.id,
        status="awaiting_approval",
        executed=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(plan)
    db.flush()
    add_event(
        db,
        "project",
        project.id,
        "github.plan_created",
        f"Pull request plan {clean_owner}/{clean_repo} {clean_head}→{clean_base} recorded (no network call).",
    )
    return plan, approval


def refresh_status(db: Session, plan: GithubPullRequest) -> GithubPullRequest:
    """Mirror the linked approval's decision; execution still never happens."""
    approval = db.get(ApprovalRequest, plan.approval_id) if plan.approval_id else None
    if approval is None:
        return plan
    if approval.status == "approved" and plan.status == "awaiting_approval":
        plan.status = "approved_not_executed"
        add_event(
            db,
            "project",
            plan.project_id,
            "github.plan_approved",
            f"Plan {plan.owner}/{plan.repo} approved; execution remains unavailable in this build.",
        )
    elif approval.status == "rejected" and plan.status in {"awaiting_approval", "approved_not_executed"}:
        plan.status = "rejected"
    db.flush()
    return plan


def decide_plan(
    db: Session,
    plan: GithubPullRequest,
    *,
    status: str,
    decided_by: str,
    note: str = "",
) -> GithubPullRequest:
    approval = db.get(ApprovalRequest, plan.approval_id) if plan.approval_id else None
    if approval is None:
        raise GithubError("This plan has no linked approval request.")
    try:
        decide_approval(db, approval, status=status, decided_by=decided_by, note=note)
    except ReviewError as exc:
        raise GithubError(str(exc)) from exc
    return refresh_status(db, plan)


def plan_payload(plan: GithubPullRequest) -> dict[str, object]:
    return {
        "id": plan.id,
        "project_id": plan.project_id,
        "owner": plan.owner,
        "repo": plan.repo,
        "repository": f"{plan.owner}/{plan.repo}",
        "base_branch": plan.base_branch,
        "head_branch": plan.head_branch,
        "title": plan.title,
        "body": plan.body,
        "status": plan.status,
        "approval_id": plan.approval_id,
        "executed": plan.executed,
        "execution_available": EXECUTION_AVAILABLE,
        "execution_reason": EXECUTION_REASON,
        "commands": build_plan_commands(plan.owner, plan.repo, plan.base_branch, plan.head_branch, plan.title),
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }
