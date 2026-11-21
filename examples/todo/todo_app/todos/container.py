"""Composition root of the todos context, independent of any delivery mechanism."""

from typing import TYPE_CHECKING

from todo_app.kernel import SystemClock, Uuid7Ids
from todo_app.persistence import Database, OutboxRelay

from .adapters.observed_todo_telemetry import ObservedTodoTelemetry
from .adapters.sqlite_todos_unit_of_work import (
    MIGRATIONS,
    OUTBOX_TABLE,
    SqliteTodosUnitOfWorkFactory,
)
from .use_cases import CreateTodo

if TYPE_CHECKING:
    from audit.backend import AuditBackend, AuditIntegrity

    from todo_app.settings import TodoSettings


class TodosDomain:
    """The todos context's use cases and the resources they hold."""

    def __init__(self, *, create: CreateTodo, relay: OutboxRelay, db: Database) -> None:
        self.create = create
        self.relay = relay
        self._db = db

    async def aclose(self) -> None:
        await self.relay.aclose()  # deliver what's pending before the connection goes
        await self._db.close()


async def build_todos(
    settings: TodoSettings,
    *,
    audit_backend: AuditBackend,
    audit_integrity: AuditIntegrity,
    poll_outbox: bool = True,
) -> TodosDomain:
    db = await Database.connect(
        settings.DB_PATH, migrations=MIGRATIONS, busy_timeout_ms=settings.DB_BUSY_TIMEOUT_MS
    )
    relay = OutboxRelay(
        db,
        OUTBOX_TABLE,
        audit_backend,
        audit_integrity,
        poll_interval=settings.OUTBOX_POLL_INTERVAL_SECONDS,
    )
    if poll_outbox:
        relay.start()
    create = CreateTodo(
        SqliteTodosUnitOfWorkFactory(db),
        ObservedTodoTelemetry(),
        clock=SystemClock(),
        ids=Uuid7Ids(),
    )
    return TodosDomain(create=create, relay=relay, db=db)
