"""Expired idempotency records are purged; live ones stay replayable."""

import asyncio
from datetime import timedelta

from todo_app.kernel import IDEMPOTENCY_TTL, IdempotencyRecord
from todo_app.persistence import ContextRuntime, Database, OutboxRelay
from todo_app.users.adapters.sql_tables import audit_outbox, idempotency
from todo_app.users.adapters.sql_users_unit_of_work import SqlUsersUnitOfWorkFactory
from todo_tests.fakes import EPOCH, FixedClock, RecordingAuditBackend

from .test_outbox_relay import CountingIntegrity


def _record(key: str, age: timedelta, now: FixedClock) -> IdempotencyRecord:
    return IdempotencyRecord(
        scope="users.register",
        key=key,
        request_fingerprint="f",
        resource_id="u1",
        created_at=now.now() - age,
    )


async def test_purge_removes_only_records_past_the_replay_window(db: Database) -> None:
    clock = FixedClock(EPOCH + timedelta(days=3))
    async with SqlUsersUnitOfWorkFactory(db)() as uow:
        await uow.idempotency.add(_record("expired", IDEMPOTENCY_TTL + timedelta(minutes=1), clock))
        await uow.idempotency.add(_record("live", IDEMPOTENCY_TTL - timedelta(minutes=1), clock))
    relay = OutboxRelay(db, audit_outbox, RecordingAuditBackend(), CountingIntegrity())
    runtime = ContextRuntime(name="users", db=db, relay=relay, idempotency=idempotency, clock=clock)

    assert await runtime.purge_expired_idempotency() == 1

    async with SqlUsersUnitOfWorkFactory(db)(read_only=True) as uow:
        assert await uow.idempotency.get("users.register", "expired") is None
        assert await uow.idempotency.get("users.register", "live") is not None


async def test_periodic_jobs_run_until_the_runtime_closes(db: Database) -> None:
    relay = OutboxRelay(db, audit_outbox, RecordingAuditBackend(), CountingIntegrity())
    runtime = ContextRuntime(name="users", db=db, relay=relay, idempotency=idempotency)
    runs = 0

    async def job() -> None:
        nonlocal runs
        runs += 1
        if runs == 1:
            raise RuntimeError("one bad run")  # logged; the loop carries on

    runtime.every(0.01, "test-job", job)
    async with asyncio.timeout(2):
        while runs < 3:  # noqa: ASYNC110 — polling a counter the job increments
            await asyncio.sleep(0.01)
    for task in runtime._tasks:
        task.cancel()

    assert runs >= 3
