"""The audit outbox is observable: backlog metrics and /health catch a stuck relay."""

import asyncio

import pytest
from asgi_lifespan import LifespanManager
from config import Settings
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from todo_app.factory import create_todo_app
from todo_app.persistence import Database, OutboxRelay
from todo_app.settings import TodoSettings
from todo_app.users.adapters.sql_tables import audit_outbox
from todo_app.users.adapters.sql_users_unit_of_work import SqlUsersUnitOfWorkFactory
from todo_tests.fakes import EPOCH, FixedClock, RecordingAuditBackend
from todo_tests.fixture_types import Metric

from .test_outbox_relay import CountingIntegrity, _entry

OUTBOX = "users_audit_outbox"


async def test_backlog_reports_pending_entries_and_the_oldest_age(
    db: Database, metric: Metric
) -> None:
    clock = FixedClock(EPOCH)
    relay = OutboxRelay(db, audit_outbox, RecordingAuditBackend(), CountingIntegrity(), clock=clock)
    async with SqlUsersUnitOfWorkFactory(db)() as uow:
        await uow.audit.record(_entry("a1"))  # occurred at EPOCH
    clock.advance(90)

    backlog = await relay.backlog()

    assert backlog.pending == 1
    assert backlog.oldest_age_seconds == pytest.approx(90)
    assert metric("todoapp_audit_outbox_pending", outbox=OUTBOX) == 1
    assert metric("todoapp_audit_outbox_oldest_age_seconds", outbox=OUTBOX) == pytest.approx(90)


async def test_an_empty_outbox_has_no_age(db: Database, metric: Metric) -> None:
    relay = OutboxRelay(db, audit_outbox, RecordingAuditBackend(), CountingIntegrity())

    backlog = await relay.backlog()

    assert (backlog.pending, backlog.oldest_age_seconds) == (0, None)
    assert metric("todoapp_audit_outbox_oldest_age_seconds", outbox=OUTBOX) == 0


async def test_deliveries_and_failures_are_counted(db: Database, metric: Metric) -> None:
    backend = RecordingAuditBackend()
    relay = OutboxRelay(db, audit_outbox, backend, CountingIntegrity())
    async with SqlUsersUnitOfWorkFactory(db)() as uow:
        await uow.audit.record(_entry("a1"))
    delivered = metric("todoapp_audit_delivered_total", outbox=OUTBOX)
    failures = metric("todoapp_audit_delivery_failures_total", outbox=OUTBOX)

    backend.fail_with = OSError("down")
    await relay.flush()
    backend.fail_with = None
    await relay.flush()

    assert metric("todoapp_audit_delivery_failures_total", outbox=OUTBOX) == failures + 1
    assert metric("todoapp_audit_delivered_total", outbox=OUTBOX) == delivered + 1


async def test_health_reports_each_context(client: AsyncClient) -> None:
    r = await client.get("/health")

    assert r.status_code == 200
    body = r.json()
    checks = body.get("checks", body)
    for name in ("users", "todos"):
        assert checks[name]["healthy"] is True
        assert checks[name]["database"] == "ok"
        assert checks[name]["audit_outbox_pending"] == 0


async def test_health_turns_503_when_audit_delivery_is_stuck(database_url: str) -> None:
    audit_sink = RecordingAuditBackend()
    app = create_todo_app(
        settings=Settings(_env_file=None, ENVIRONMENT="test", LOG_LEVEL="WARNING"),  # type: ignore[call-arg]
        todo_settings=TodoSettings(  # type: ignore[call-arg]
            _env_file=None,
            DATABASE_URL=SecretStr(database_url),
            OUTBOX_POLL_INTERVAL_SECONDS=3600,
            OUTBOX_MAX_AGE_SECONDS=0.05,
        ),
        audit_backend=audit_sink,
    )
    audit_sink.fail_with = OSError("audit sink down")

    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/v1/users/", json={"email": "ada@example.com", "name": "Ada"})
            assert r.status_code == 201  # the outage doesn't fail the request...
            await asyncio.sleep(0.1)  # ...but the entry now waits past the 50 ms limit
            health = await client.get("/health")

    assert health.status_code == 503
    body = health.json()
    checks = body.get("checks", body)
    assert checks["users"]["healthy"] is False
    assert checks["users"]["audit_outbox_pending"] == 1
    assert checks["todos"]["healthy"] is True
