from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import OrchestratorWorkerSlot
from app.run_lock import acquire_run_lock, release_run_lock
from app.worker_slots import (
    MAX_WORKER_SLOTS,
    acquire_worker_slots,
    active_worker_slots,
    release_worker_slots,
    renew_worker_slots,
)

UTC = timezone.utc


def _factory(tmp_path):
    client = TestClient(
        create_app(
            f"sqlite:///{(tmp_path / 'worker-slots.sqlite3').as_posix()}",
            allowed_hosts=["testserver"],
        )
    )
    client.__enter__()
    return client


def test_shared_worker_slots_are_bounded_expiring_and_owner_checked(tmp_path) -> None:
    client = _factory(tmp_path)
    try:
        first = client.app.state.session_factory()
        second = client.app.state.session_factory()
        now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
        try:
            assert acquire_worker_slots(first, "process-a", limit=2, lease_seconds=10, now=now) == [1, 2]
            assert acquire_worker_slots(second, "process-b", limit=2, lease_seconds=10, now=now) == []
            assert [slot.owner for slot in active_worker_slots(second, now=now)] == ["process-a", "process-a"]

            assert renew_worker_slots(first, "process-a", lease_seconds=10, now=now + timedelta(seconds=5)) == 2
            assert acquire_worker_slots(second, "process-b", limit=2, lease_seconds=10, now=now + timedelta(seconds=11)) == []
            assert acquire_worker_slots(second, "process-b", limit=2, lease_seconds=10, now=now + timedelta(seconds=16)) == [1, 2]
            assert renew_worker_slots(first, "process-a", lease_seconds=10, now=now + timedelta(seconds=16)) == 0
            assert release_worker_slots(first, "process-a") == 0
            assert release_worker_slots(second, "process-b") == 2
            assert active_worker_slots(first, now=now + timedelta(seconds=16)) == []
        finally:
            first.close()
            second.close()
    finally:
        client.__exit__(None, None, None)


def test_worker_slot_capacity_is_bounded_even_for_bad_configuration(tmp_path) -> None:
    client = _factory(tmp_path)
    try:
        with client.app.state.session_factory() as db:
            assert acquire_worker_slots(db, "bounded", limit=MAX_WORKER_SLOTS + 50, lease_seconds=30)
            assert len(active_worker_slots(db)) == MAX_WORKER_SLOTS
            assert acquire_worker_slots(db, "zero", limit=0, lease_seconds=30) == []
            assert db.query(OrchestratorWorkerSlot).count() == MAX_WORKER_SLOTS
            assert release_worker_slots(db, "bounded") == MAX_WORKER_SLOTS
    finally:
        client.__exit__(None, None, None)


def test_worker_permits_and_workspace_mutation_gate_are_mutually_exclusive(tmp_path) -> None:
    client = _factory(tmp_path)
    try:
        with client.app.state.session_factory() as mutation_db:
            with client.app.state.session_factory() as worker_db:
                assert acquire_worker_slots(worker_db, "active-run", limit=2, lease_seconds=30) == [1, 2]
                assert not acquire_run_lock(mutation_db, "workspace-change", lease_seconds=30)
                assert release_worker_slots(worker_db, "active-run") == 2
                assert acquire_run_lock(mutation_db, "workspace-change", lease_seconds=30)
                assert acquire_worker_slots(worker_db, "blocked-run", limit=2, lease_seconds=30) == []
                assert release_run_lock(mutation_db, "workspace-change")
                assert acquire_worker_slots(worker_db, "next-run", limit=2, lease_seconds=30) == [1, 2]
                assert release_worker_slots(worker_db, "next-run") == 2
    finally:
        client.__exit__(None, None, None)


def test_expired_worker_permit_cannot_be_renewed_through_mutation_gate(tmp_path) -> None:
    client = _factory(tmp_path)
    try:
        now = datetime.now(UTC)
        with client.app.state.session_factory() as worker_db:
            assert acquire_worker_slots(worker_db, "expired-run", limit=1, lease_seconds=1, now=now) == [1]

        with client.app.state.session_factory() as mutation_db:
            assert acquire_run_lock(mutation_db, "workspace-change", lease_seconds=30, now=now + timedelta(seconds=2))
            with client.app.state.session_factory() as worker_db:
                assert renew_worker_slots(worker_db, "expired-run", lease_seconds=30, now=now + timedelta(seconds=2)) == 0
            assert release_run_lock(mutation_db, "workspace-change")
    finally:
        client.__exit__(None, None, None)


def test_simultaneous_worker_and_mutation_reservations_cannot_both_win(tmp_path) -> None:
    client = _factory(tmp_path)
    try:
        factory = client.app.state.session_factory
        gate = Barrier(2)

        def reserve_workers() -> list[int]:
            with factory() as db:
                gate.wait(timeout=5)
                return acquire_worker_slots(db, "racing-run", limit=2, lease_seconds=30)

        def reserve_mutation() -> bool:
            with factory() as db:
                gate.wait(timeout=5)
                return acquire_run_lock(db, "racing-mutation", lease_seconds=30)

        with ThreadPoolExecutor(max_workers=2) as pool:
            workers_future = pool.submit(reserve_workers)
            mutation_future = pool.submit(reserve_mutation)
            worker_slots = workers_future.result(timeout=10)
            mutation_lock = mutation_future.result(timeout=10)

        assert bool(worker_slots) != mutation_lock
        with factory() as db:
            if worker_slots:
                assert len(active_worker_slots(db)) == len(worker_slots)
                release_worker_slots(db, "racing-run")
            if mutation_lock:
                assert release_run_lock(db, "racing-mutation")
    finally:
        client.__exit__(None, None, None)


def test_simultaneous_processes_cannot_overbook_shared_worker_slots(tmp_path) -> None:
    client = _factory(tmp_path)
    try:
        factory = client.app.state.session_factory
        gate = Barrier(2)

        def reserve(owner: str) -> list[int]:
            with factory() as db:
                gate.wait(timeout=5)
                return acquire_worker_slots(db, owner, limit=3, lease_seconds=30)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reserve, "process-a"), pool.submit(reserve, "process-b")]
            allocations = [future.result(timeout=10) for future in futures]

        claimed = [slot for allocation in allocations for slot in allocation]
        assert len(claimed) == 3
        assert sorted(claimed) == [1, 2, 3]
        with factory() as db:
            owners = [slot.owner for slot in active_worker_slots(db)]
            assert len(owners) == 3
            assert set(owners) in ({"process-a"}, {"process-b"})
            release_worker_slots(db, "process-a")
            release_worker_slots(db, "process-b")
    finally:
        client.__exit__(None, None, None)
