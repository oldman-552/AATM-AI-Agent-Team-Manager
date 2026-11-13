"""PostgreSQL smoke coverage enabled by AATM_TEST_POSTGRES_URL in CI."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db import build_engine, make_session_factory
from app.migrate import upgrade_database
from app.models import OrchestratorRunLock, OrchestratorWorkerSlot
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
        finally:
            first.close()
            second.close()
    finally:
        engine.dispose()
