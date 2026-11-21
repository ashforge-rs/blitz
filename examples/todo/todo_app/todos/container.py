"""Composition root of the todos context, independent of any delivery mechanism."""

from typing import TYPE_CHECKING

from todo_app.kernel import StorageUnavailableError, SystemClock, Uuid7Ids
from todo_app.persistence import Database, OutboxRelay

from .adapters import sql_migrations
from .adapters.observed_todo_telemetry import ObservedTodoTelemetry
from .adapters.sql_tables import audit_outbox
from .adapters.sql_todos_unit_of_work import SqlTodosUnitOfWorkFactory
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

    async def health(self, *, max_outbox_age_s: float) -> dict[str, object]:
        """For blitz's /health: the database answers and audit delivery keeps up."""
        try:
            backlog = await self.relay.backlog()
        except StorageUnavailableError:
            return {"name": "todos", "healthy": False, "database": "unavailable"}
        age = backlog.oldest_age_seconds
        return {
            "name": "todos",
            "healthy": age is None or age <= max_outbox_age_s,
            "database": "ok",
            "audit_outbox_pending": backlog.pending,
            "audit_outbox_oldest_age_seconds": round(age or 0.0, 1),
        }

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
        settings.DATABASE_URL.get_secret_value(),
        busy_timeout_ms=settings.DB_BUSY_TIMEOUT_MS,
        connect_timeout_s=settings.DB_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        if settings.DB_MIGRATE_ON_STARTUP:
            await sql_migrations.upgrade(db)
        else:
            await sql_migrations.ensure_at_head(db)
    except BaseException:
        await db.close()
        raise
    relay = OutboxRelay(
        db,
        audit_outbox,
        audit_backend,
        audit_integrity,
        poll_interval=settings.OUTBOX_POLL_INTERVAL_SECONDS,
    )
    if poll_outbox:
        relay.start()
    create = CreateTodo(
        SqlTodosUnitOfWorkFactory(db),
        ObservedTodoTelemetry(),
        clock=SystemClock(),
        ids=Uuid7Ids(),
    )
    return TodosDomain(create=create, relay=relay, db=db)
