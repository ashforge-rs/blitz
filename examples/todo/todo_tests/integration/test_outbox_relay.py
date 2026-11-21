"""The relay delivers committed audit entries, in order, at least once."""

import asyncio

import pytest
from audit.backend import AuditEvent, AuditIntegrity, AuditResult

from todo_app.kernel import Actor, AuditOutcome, AuditRecord
from todo_app.persistence import Database, OutboxRelay
from todo_app.users.adapters.sqlite_users_unit_of_work import (
    OUTBOX_TABLE,
    SqliteUsersUnitOfWorkFactory,
)
from todo_tests.fakes import EPOCH, RecordingAuditBackend

ACTOR = Actor(user_id="u1", correlation_id="req-1", client_address="10.0.0.1:5000", entrypoint="/x")


class CountingIntegrity(AuditIntegrity):
    def __init__(self) -> None:
        self.applied: list[str] = []

    def add_integrity(self, event: AuditEvent) -> None:
        self.applied.append(str(event.metadata["audit_id"]))


def _entry(entry_id: str, outcome: AuditOutcome = AuditOutcome.SUCCESS) -> AuditRecord:
    return AuditRecord(
        id=entry_id,
        operation="users.register",
        outcome=outcome,
        actor=ACTOR,
        occurred_at=EPOCH,
        resource_id="u1",
        details={"reason": "x"},
    )


async def _commit(db: Database, *entries: AuditRecord) -> None:
    async with SqliteUsersUnitOfWorkFactory(db)() as uow:
        for entry in entries:
            await uow.audit.record(entry)


async def _pending(db: Database) -> int:
    row = await db.query(lambda c: c.execute(f"SELECT count(*) FROM {OUTBOX_TABLE}").fetchone())  # noqa: S608 — constant
    return int(row[0])


@pytest.fixture
def backend() -> RecordingAuditBackend:
    return RecordingAuditBackend()


@pytest.fixture
def relay(db: Database, backend: RecordingAuditBackend) -> OutboxRelay:
    return OutboxRelay(db, OUTBOX_TABLE, backend, CountingIntegrity(), poll_interval=0.01)


async def test_delivers_committed_entries_in_order_then_removes_them(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    await _commit(db, _entry("a1"), _entry("a2", AuditOutcome.FAILURE))

    assert await relay.flush() == 2

    first, second = backend.events
    assert [e.metadata["audit_id"] for e in backend.events] == ["a1", "a2"]
    assert (first.method, first.result, first.principal) == (
        "users.register",
        AuditResult.SUCCESS,
        "u1",
    )
    assert (first.correlation_id, first.remote_addr, first.path) == ("req-1", "10.0.0.1:5000", "/x")
    assert first.metadata["resource_id"] == "u1"
    assert first.metadata["reason"] == "x"
    assert second.result is AuditResult.FAILURE
    assert await _pending(db) == 0


async def test_rolled_back_entries_are_never_delivered(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    async def failing_unit() -> None:
        async with SqliteUsersUnitOfWorkFactory(db)() as uow:
            await uow.audit.record(_entry("a1"))
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_unit()

    assert await relay.flush() == 0
    assert backend.events == []


async def test_an_unavailable_backend_delays_delivery_without_losing_entries(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    await _commit(db, _entry("a1"), _entry("a2"))
    backend.fail_with = OSError("audit sink down")

    assert await relay.flush() == 0
    assert await _pending(db) == 2

    backend.fail_with = None
    assert await relay.flush() == 2
    assert [e.metadata["audit_id"] for e in backend.events] == ["a1", "a2"]


async def test_integrity_is_applied_in_delivery_order(
    db: Database, backend: RecordingAuditBackend
) -> None:
    integrity = CountingIntegrity()
    relay = OutboxRelay(db, OUTBOX_TABLE, backend, integrity)
    await _commit(db, _entry("a1"), _entry("a2"), _entry("a3"))

    await relay.flush()

    assert integrity.applied == ["a1", "a2", "a3"]


async def test_the_background_loop_delivers_without_being_asked(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    relay.start()
    await _commit(db, _entry("a1"))

    async with asyncio.timeout(2):
        while not backend.events:  # noqa: ASYNC110 — polling an external backend's state
            await asyncio.sleep(0.01)
    await relay.aclose()

    assert [e.metadata["audit_id"] for e in backend.events] == ["a1"]


async def test_close_makes_a_last_delivery_attempt(
    db: Database, backend: RecordingAuditBackend
) -> None:
    relay = OutboxRelay(db, OUTBOX_TABLE, backend, CountingIntegrity(), poll_interval=3600)
    relay.start()
    await asyncio.sleep(0)  # let the first (empty) cycle run
    await _commit(db, _entry("a1"))

    await relay.aclose()

    assert [e.metadata["audit_id"] for e in backend.events] == ["a1"]


def test_table_names_are_checked() -> None:
    with pytest.raises(ValueError, match="invalid table name"):
        OutboxRelay(None, "x; DROP TABLE users", RecordingAuditBackend(), CountingIntegrity())  # type: ignore[arg-type]  # rejected before db is used
