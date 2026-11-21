"""The relay delivers committed audit entries, in order, at least once (every SQL backend)."""

import asyncio

import pytest
from audit.backend import AuditEvent, AuditIntegrity, AuditResult
from audit.integrity import SequenceIntegrity
from sqlalchemy import func, select

from todo_app.kernel import Actor, AuditOutcome, AuditRecord
from todo_app.persistence import Database, OutboxRelay
from todo_app.users.adapters.sql_tables import audit_outbox
from todo_app.users.adapters.sql_users_unit_of_work import SqlUsersUnitOfWorkFactory
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
    async with SqlUsersUnitOfWorkFactory(db)() as uow:
        for entry in entries:
            await uow.audit.record(entry)


async def _pending(db: Database) -> int:
    async with db.transaction(read_only=True) as conn:
        return int(
            (await conn.execute(select(func.count()).select_from(audit_outbox))).scalar_one()
        )


@pytest.fixture
def backend() -> RecordingAuditBackend:
    return RecordingAuditBackend()


@pytest.fixture
def relay(db: Database, backend: RecordingAuditBackend) -> OutboxRelay:
    return OutboxRelay(db, audit_outbox, backend, CountingIntegrity(), poll_interval=0.01)


def _ids(backend: RecordingAuditBackend) -> list[object]:
    return [e.metadata["audit_id"] for e in backend.events]


async def test_delivers_committed_entries_in_order_then_removes_them(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    await _commit(db, _entry("a1"), _entry("a2", AuditOutcome.FAILURE))

    assert await relay.flush() == 2

    first, second = backend.events
    assert _ids(backend) == ["a1", "a2"]
    assert (first.method, first.result, first.principal) == (
        "users.register",
        AuditResult.SUCCESS,
        "u1",
    )
    assert (first.correlation_id, first.remote_addr, first.path) == ("req-1", "10.0.0.1:5000", "/x")
    assert first.metadata["resource_id"] == "u1"
    assert first.metadata["reason"] == "x"
    assert first.metadata["occurred_at"] == EPOCH.isoformat()
    assert second.result is AuditResult.FAILURE
    assert await _pending(db) == 0


async def test_rolled_back_entries_are_never_delivered(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    async def failing_unit() -> None:
        async with SqlUsersUnitOfWorkFactory(db)() as uow:
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
    assert _ids(backend) == ["a1", "a2"]


async def test_integrity_is_applied_in_delivery_order(
    db: Database, backend: RecordingAuditBackend
) -> None:
    integrity = CountingIntegrity()
    relay = OutboxRelay(db, audit_outbox, backend, integrity)
    await _commit(db, _entry("a1"), _entry("a2"), _entry("a3"))

    await relay.flush()

    assert integrity.applied == ["a1", "a2", "a3"]


async def test_the_background_loop_delivers_without_being_asked(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    relay.start()
    await _commit(db, _entry("a1"))

    async with asyncio.timeout(5):
        while not backend.events:  # noqa: ASYNC110 — polling an external backend's state
            await asyncio.sleep(0.01)
    await relay.aclose()

    assert _ids(backend) == ["a1"]


async def test_close_makes_a_last_delivery_attempt(
    db: Database, backend: RecordingAuditBackend
) -> None:
    relay = OutboxRelay(db, audit_outbox, backend, CountingIntegrity(), poll_interval=3600)
    relay.start()
    await asyncio.sleep(0)  # let the first (empty) cycle run
    await _commit(db, _entry("a1"))

    await relay.aclose()

    assert _ids(backend) == ["a1"]


async def test_a_retried_delivery_keeps_integrity_sequence_numbers_gap_free(
    db: Database, backend: RecordingAuditBackend
) -> None:
    relay = OutboxRelay(db, audit_outbox, backend, SequenceIntegrity())
    await _commit(db, _entry("a1"), _entry("a2"))

    backend.fail_with = OSError("audit sink down")
    await relay.flush()  # a1 is prepared (sequence 1) but not accepted
    backend.fail_with = None
    await relay.flush()

    assert [e.metadata["sequence"] for e in backend.events] == [1, 2]
    assert _ids(backend) == ["a1", "a2"]


async def test_events_carry_their_outbox_sequence(
    db: Database, relay: OutboxRelay, backend: RecordingAuditBackend
) -> None:
    await _commit(db, _entry("a1"), _entry("a2"))

    await relay.flush()

    first, second = (int(str(e.metadata["outbox_seq"])) for e in backend.events)
    assert second > first
