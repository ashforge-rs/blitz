from typing import TYPE_CHECKING

from todo_app.kernel import StorageUnavailableError

from .database import Database
from .outbox_relay import OutboxRelay

if TYPE_CHECKING:
    from audit.backend import AuditBackend, AuditIntegrity
    from sqlalchemy import Table

    from todo_app.settings import TodoSettings

    from .migrations import ContextMigrations


class ContextRuntime:
    """What every context holds at runtime: its database and its audit relay."""

    def __init__(self, *, name: str, db: Database, relay: OutboxRelay) -> None:
        self.name = name
        self.db = db
        self.relay = relay

    async def health(self, *, max_outbox_age_s: float) -> dict[str, object]:
        """For blitz's /health: the database answers and audit delivery keeps up."""
        try:
            backlog = await self.relay.backlog()
        except StorageUnavailableError:
            return {"name": self.name, "healthy": False, "database": "unavailable"}
        age = backlog.oldest_age_seconds
        return {
            "name": self.name,
            "healthy": age is None or age <= max_outbox_age_s,
            "database": "ok",
            "audit_outbox_pending": backlog.pending,
            "audit_outbox_oldest_age_seconds": round(age or 0.0, 1),
        }

    async def aclose(self) -> None:
        await self.relay.aclose()  # deliver what's pending before the connection goes
        await self.db.close()


async def open_context_runtime(
    name: str,
    settings: TodoSettings,
    *,
    migrations: ContextMigrations,
    outbox: Table,
    audit_backend: AuditBackend,
    audit_integrity: AuditIntegrity,
    poll_outbox: bool,
) -> ContextRuntime:
    """Connect, migrate (or check the schema is at head) and start the relay.

    ``poll_outbox=False`` (short-lived processes such as the CLI) delivers audit
    entries only when the runtime is closed.
    """
    db = await Database.connect(
        settings.DATABASE_URL.get_secret_value(),
        busy_timeout_ms=settings.DB_BUSY_TIMEOUT_MS,
        connect_timeout_s=settings.DB_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        if settings.DB_MIGRATE_ON_STARTUP:
            await migrations.upgrade(db)
        else:
            await migrations.ensure_at_head(db)
    except BaseException:
        await db.close()
        raise
    relay = OutboxRelay(
        db,
        outbox,
        audit_backend,
        audit_integrity,
        poll_interval=settings.OUTBOX_POLL_INTERVAL_SECONDS,
    )
    if poll_outbox:
        relay.start()
    return ContextRuntime(name=name, db=db, relay=relay)
