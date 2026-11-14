"""PostgreSQL smoke coverage enabled by AATM_TEST_POSTGRES_URL in CI."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db import build_engine, make_session_factory
from app.migrate import upgrade_database
from app.models import Agent, OrchestratorRunLock, OrchestratorWorkerSlot, Task, TaskTransition
from app.orchestrator import claim_task
from app.run_lock import acquire_run_lock, release_run_lock
from app.worker_slots import acquire_worker_slots, active_worker_slots, release_worker_slots

POSTGRES_URL = os.getenv("AATM_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="AATM_TEST_POSTGRES_URL is not configured")
def test_postgresql_migrations_and_shared_run_lock() -> None:
    assert POSTGRES_URL is not None
    engine = build_engine(POSTGRES_URL)
    try:
        upgrade_database(engine, POSTGRES_URL)
        factory = make_session_factory(engine)
        first = factory()
        second = factory()
        try:
            seeded = first.scalar(select(OrchestratorRunLock).where(OrchestratorRunLock.id == "global"))
            assert seeded is not None
            now = datetime.now(timezone.utc)
            assert acquire_run_lock(first, "postgres-worker-a", lease_seconds=30, now=now)
            assert not acquire_run_lock(second, "postgres-worker-b", lease_seconds=30, now=now)
            assert release_run_lock(first, "postgres-worker-a")
            assert acquire_run_lock(second, "postgres-worker-b", lease_seconds=30, now=now)
            assert release_run_lock(second, "postgres-worker-b")

            seeded_slots = first.scalars(select(OrchestratorWorkerSlot).order_by(OrchestratorWorkerSlot.id)).all()
            assert len(seeded_slots) == 20
            assert acquire_worker_slots(first, "postgres-worker-a", limit=3, lease_seconds=30, now=now) == [1, 2, 3]
            assert acquire_worker_slots(second, "postgres-worker-b", limit=3, lease_seconds=30, now=now) == []
            assert len(active_worker_slots(second, now=now)) == 3
            assert release_worker_slots(first, "postgres-worker-a") == 3
            assert acquire_worker_slots(second, "postgres-worker-b", limit=3, lease_seconds=30, now=now) == [1, 2, 3]
            assert release_worker_slots(second, "postgres-worker-b") == 3

            slot_barrier = Barrier(2)

            def reserve_slots(owner: str) -> list[int]:
                with factory() as db:
                    slot_barrier.wait(timeout=5)
                    return acquire_worker_slots(db, owner, limit=4, lease_seconds=30)

            with ThreadPoolExecutor(max_workers=2) as pool:
                reservations = list(pool.map(reserve_slots, ["postgres-race-a", "postgres-race-b"]))
            reserved_ids = [slot_id for reservation in reservations for slot_id in reservation]
            assert len(reserved_ids) == 4
            assert sorted(reserved_ids) == [1, 2, 3, 4]
            assert release_worker_slots(first, "postgres-race-a") + release_worker_slots(second, "postgres-race-b") == 4
            assert acquire_worker_slots(first, "postgres-active", limit=1, lease_seconds=30) == [1]
            assert not acquire_run_lock(second, "postgres-mutation", lease_seconds=30)
            assert release_worker_slots(first, "postgres-active") == 1
            assert acquire_run_lock(second, "postgres-mutation", lease_seconds=30)
            assert acquire_worker_slots(first, "postgres-blocked", limit=1, lease_seconds=30) == []
            assert release_run_lock(second, "postgres-mutation")

            agent_id = str(uuid4())
            task_id = str(uuid4())
            first.add(Agent(id=agent_id, name=f"Worker {agent_id}", role="Test worker"))
            first.add(Task(id=task_id, title="Atomic claim", state="assigned", assigned_agent_id=agent_id))
            first.commit()
            claim_barrier = Barrier(2)

            def compete_for_task(owner: str) -> bool:
                with factory() as db:
                    candidate = db.get(Task, task_id)
                    assert candidate is not None
                    claim_barrier.wait(timeout=5)
                    claimed = claim_task(db, candidate, owner=owner, lease_seconds=60)
                    db.commit()
                    return claimed

            with ThreadPoolExecutor(max_workers=2) as pool:
                claim_results = list(pool.map(compete_for_task, ["postgres-claim-a", "postgres-claim-b"]))
            assert sorted(claim_results) == [False, True]
            claimed_task = first.get(Task, task_id)
            assert claimed_task is not None
            first.refresh(claimed_task)
            assert claimed_task.state == "running"
            assert claimed_task.lease_owner in {"postgres-claim-a", "postgres-claim-b"}
            assert len(first.scalars(
                select(TaskTransition).where(
                    TaskTransition.task_id == task_id,
                    TaskTransition.to_state == "running",
                )
            ).all()) == 1
            first.rollback()
        finally:
            first.close()
            second.close()
    finally:
        engine.dispose()
