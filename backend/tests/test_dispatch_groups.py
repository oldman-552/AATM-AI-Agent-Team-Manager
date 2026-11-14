from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from fastapi.testclient import TestClient

from app.dispatch_groups import (
    acquire_dispatch_group,
    active_dispatch_groups,
    release_dispatch_group,
    release_dispatch_groups,
    renew_dispatch_groups,
)
from app.main import create_app
from app.run_lock import acquire_run_lock, release_run_lock

UTC = timezone.utc


def _client(tmp_path):
    client = TestClient(
        create_app(
            f"sqlite:///{(tmp_path / 'dispatch-groups.sqlite3').as_posix()}",
            allowed_hosts=["testserver"],
        )
    )
    client.__enter__()
    return client


def test_dispatch_group_leases_are_exclusive_expiring_and_owner_checked(tmp_path) -> None:
    client = _client(tmp_path)
    try:
        factory = client.app.state.session_factory
        now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
        with factory() as owner_db, factory() as contender_db:
            assert acquire_dispatch_group(owner_db, "project:alpha", "run-a", lease_seconds=10, now=now)
            assert not acquire_dispatch_group(contender_db, "project:alpha", "run-b", lease_seconds=10, now=now)
            assert [lease.owner for lease in active_dispatch_groups(contender_db, now=now)] == ["run-a"]

            assert renew_dispatch_groups(owner_db, "run-a", lease_seconds=10, now=now + timedelta(seconds=5)) == 1
            assert not acquire_dispatch_group(contender_db, "project:alpha", "run-b", lease_seconds=10, now=now + timedelta(seconds=11))
            assert renew_dispatch_groups(owner_db, "run-a", lease_seconds=10, now=now + timedelta(seconds=16)) == 0
            assert acquire_dispatch_group(contender_db, "project:alpha", "run-b", lease_seconds=10, now=now + timedelta(seconds=16))
            assert renew_dispatch_groups(owner_db, "run-a", lease_seconds=10, now=now + timedelta(seconds=16)) == 0
            assert not release_dispatch_group(owner_db, "project:alpha", "run-a")
            assert release_dispatch_groups(contender_db, "run-b") == 1
            assert active_dispatch_groups(owner_db, now=now + timedelta(seconds=16)) == []
    finally:
        client.__exit__(None, None, None)


def test_dispatch_group_reservation_can_be_made_by_live_run_owner(tmp_path) -> None:
    client = _client(tmp_path)
    try:
        factory = client.app.state.session_factory
        with factory() as db:
            assert acquire_run_lock(db, "api-run-a", lease_seconds=30)
            assert acquire_dispatch_group(db, "project:alpha", "api-run-a", lease_seconds=30)
            assert not acquire_dispatch_group(db, "project:beta", "unrelated", lease_seconds=30)
            assert release_dispatch_groups(db, "api-run-a") == 1
            assert release_run_lock(db, "api-run-a")
    finally:
        client.__exit__(None, None, None)


def test_live_group_lease_blocks_workspace_mutation_after_run_lock_release(tmp_path) -> None:
    client = _client(tmp_path)
    try:
        factory = client.app.state.session_factory
        with factory() as run_db:
            assert acquire_run_lock(run_db, "api-run", lease_seconds=30)
            assert acquire_dispatch_group(run_db, "project:alpha", "api-run", lease_seconds=30)
            assert release_run_lock(run_db, "api-run")

        with factory() as mutation_db:
            assert not acquire_run_lock(mutation_db, "workspace-edit", lease_seconds=30)

        with factory() as run_db:
            assert release_dispatch_groups(run_db, "api-run") == 1
        with factory() as mutation_db:
            assert acquire_run_lock(mutation_db, "workspace-edit", lease_seconds=30)
            assert release_run_lock(mutation_db, "workspace-edit")
    finally:
        client.__exit__(None, None, None)


def test_group_reservation_and_mutation_gate_race_cannot_both_win(tmp_path) -> None:
    client = _client(tmp_path)
    try:
        factory = client.app.state.session_factory
        start = Barrier(2)

        def reserve_group() -> bool:
            with factory() as db:
                start.wait(timeout=5)
                return acquire_dispatch_group(db, "project:race", "dispatch", lease_seconds=30)

        def reserve_mutation() -> bool:
            with factory() as db:
                start.wait(timeout=5)
                return acquire_run_lock(db, "workspace-edit", lease_seconds=30)

        with ThreadPoolExecutor(max_workers=2) as pool:
            group = pool.submit(reserve_group)
            mutation = pool.submit(reserve_mutation)
            group_won = group.result(timeout=10)
            mutation_won = mutation.result(timeout=10)

        assert group_won != mutation_won
        with factory() as db:
            if group_won:
                assert release_dispatch_groups(db, "dispatch") == 1
            if mutation_won:
                assert release_run_lock(db, "workspace-edit")
    finally:
        client.__exit__(None, None, None)
