from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import OrchestratorWorkerSlot
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
