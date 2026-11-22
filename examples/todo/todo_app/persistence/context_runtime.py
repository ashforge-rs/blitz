import asyncio
import contextlib
from typing import TYPE_CHECKING

from loguru import logger

from todo_app.kernel import IDEMPOTENCY_TTL, StorageUnavailableError, SystemClock

from .database import Database
from .outbox_relay import OutboxRelay
from .sql_idempotency_store import purge_expired

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from audit.backend import AuditBackend, AuditIntegrity
    from sqlalchemy import Table

    from todo_app.kernel import Clock
    from todo_app.settings import TodoSettings

    from .migrations import ContextMigrations


class ContextRuntime:
    """What every context holds at runtime: its database, audit relay and housekeeping."""

    def __init__(
        self,
        *,
        name: str,
        db: Database,
        relay: OutboxRelay,
        idempotency: Table,
        clock: Clock | None = None,
    ) -> None:
        self.name = name
        self.db = db
        self.relay = relay
        self._idempotency = idempotency
        self._clock = clock or SystemClock()
        self._tasks: list[asyncio.Task[None]] = []

    def every(self, interval_s: float, name: str, job: Callable[[], Awaitable[object]]) -> None:
        """Run ``job`` now and then every ``interval_s`` until the runtime closes.

        A failing run is logged and retried next time: background work must not die.
        """

        async def _loop() -> None:
            while True:
                try:
                    await job()
                except Exception as exc:  # noqa: BLE001 — a background task must not die
                    logger.warning("background.job_failed", job=name, error=str(exc))
                await asyncio.sleep(interval_s)

        self._tasks.append(asyncio.create_task(_loop(), name=f"{self.name}:{name}"))

    def start_housekeeping(self, interval_s: float) -> None:
        """Purge expired idempotency records every ``interval_s`` (long-running processes)."""
        self.every(interval_s, "idempotency-purge", self.purge_expired_idempotency)

    async def purge_expired_idempotency(self) -> int:
        cutoff = self._clock.now() - IDEMPOTENCY_TTL
        async with self.db.transaction() as conn:
            purged = await purge_expired(conn, self._idempotency, created_before=cutoff)
        if purged:
            logger.info("idempotency.purged", context=self.name, records=purged)
        return purged

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
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self.relay.aclose()  # deliver what's pending before the connection goes
        await self.db.close()


async def open_context_runtime(
    name: str,
    settings: TodoSettings,
    *,
    migrations: ContextMigrations,
    outbox: Table,
    idempotency: Table,
    audit_backend: AuditBackend,
    audit_integrity: AuditIntegrity,
    poll_outbox: bool,
) -> ContextRuntime:
    """Connect, migrate (or check the schema is at head) and start the relay.

    ``poll_outbox=False`` (short-lived processes such as the CLI) delivers audit
    entries only when the runtime is closed and runs no housekeeping.
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
    runtime = ContextRuntime(name=name, db=db, relay=relay, idempotency=idempotency)
    if poll_outbox:
        relay.start()
        runtime.start_housekeeping(settings.IDEMPOTENCY_PURGE_INTERVAL_SECONDS)
    return runtime
