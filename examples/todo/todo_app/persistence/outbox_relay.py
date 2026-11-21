import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from audit.backend import AuditEvent, AuditEventType, AuditResult, AuditSeverity
from loguru import logger
from metrics import counter
from prometheus_client import Gauge
from sqlalchemy import delete, func, select

from todo_app.kernel import Actor, AuditOutcome, AuditRecord, SystemClock

if TYPE_CHECKING:
    from audit.backend import AuditBackend, AuditIntegrity
    from sqlalchemy import RowMapping, Table

    from todo_app.kernel import Clock

    from .database import Database


#: Undelivered entries per outbox; alert when the oldest grows (see grafana/alerts.yml).
OUTBOX_PENDING = Gauge(
    "todoapp_audit_outbox_pending", "Audit entries waiting for delivery", ["outbox"]
)
OUTBOX_OLDEST_AGE = Gauge(
    "todoapp_audit_outbox_oldest_age_seconds",
    "Age of the oldest undelivered audit entry (0 when the outbox is empty)",
    ["outbox"],
)
AUDIT_DELIVERED = counter(
    "todoapp_audit_delivered_total", "Audit entries delivered to the audit backend", ["outbox"]
)
AUDIT_DELIVERY_FAILURES = counter(
    "todoapp_audit_delivery_failures_total",
    "Failed attempts to deliver an audit entry (it stays in the outbox)",
    ["outbox"],
)


@dataclass(frozen=True, slots=True)
class Backlog:
    pending: int
    #: ``None`` when nothing is pending.
    oldest_age_seconds: float | None


def to_audit_event(record: AuditRecord) -> AuditEvent:
    """The blitz ``AuditEvent`` for a recorded entry (same shape as ``log_operation``)."""
    success = record.outcome is AuditOutcome.SUCCESS
    metadata: dict[str, object] = {
        "operation": record.operation,
        "audit_id": record.id,
        "occurred_at": record.occurred_at.isoformat(),
        **record.details,
    }
    if record.resource_id is not None:
        metadata["resource_id"] = record.resource_id
    return AuditEvent(
        event_type=AuditEventType.ADMIN_ACTION,
        severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
        result=AuditResult.SUCCESS if success else AuditResult.FAILURE,
        principal=record.actor.user_id,
        remote_addr=record.actor.client_address,
        correlation_id=record.actor.correlation_id,
        method=record.operation,
        path=record.actor.entrypoint,
        metadata=metadata,
    )


class OutboxRelay:
    """Delivers outbox entries to the audit backend, oldest first, at least once.

    An entry is deleted only after the backend accepted it, so a crash or a
    backend outage delays delivery but never loses an entry.  A crash right
    after delivery, or two app instances relaying at once, can repeat one;
    ``metadata["audit_id"]`` identifies the duplicate.
    """

    def __init__(
        self,
        db: Database,
        table: Table,
        backend: AuditBackend,
        integrity: AuditIntegrity,
        *,
        poll_interval: float = 0.5,
        batch_size: int = 100,
        clock: Clock | None = None,
    ) -> None:
        self._db = db
        self._table = table
        self._backend = backend
        self._integrity = integrity
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._clock = clock or SystemClock()
        self._flush_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"outbox-relay:{self._table.name}")

    async def flush(self) -> int:
        """Deliver pending entries now; returns how many were delivered."""
        async with self._flush_lock:
            delivered = 0
            while batch := await self._pending():
                for row in batch:
                    event = to_audit_event(_to_record(row))
                    self._integrity.add_integrity(event)
                    try:
                        await self._backend.log(event)
                    except Exception as exc:  # noqa: BLE001 — keep the entry; retry next cycle
                        AUDIT_DELIVERY_FAILURES.labels(outbox=self._table.name).inc()
                        logger.warning(
                            "audit.outbox.delivery_failed", table=self._table.name, error=str(exc)
                        )
                        return delivered
                    async with self._db.transaction() as conn:
                        await conn.execute(
                            delete(self._table).where(self._table.c.seq == row["seq"])
                        )
                    AUDIT_DELIVERED.labels(outbox=self._table.name).inc()
                    delivered += 1
            return delivered

    async def backlog(self) -> Backlog:
        """What is waiting.  Also refreshes the backlog gauges."""
        t = self._table
        async with self._db.transaction(read_only=True) as conn:
            row = (
                await conn.execute(select(func.count(), func.min(t.c.occurred_at)).select_from(t))
            ).one()
        pending, oldest = int(row[0]), row[1]
        age = None
        if oldest is not None:
            if isinstance(oldest, str):  # SQLite's MIN() returns the stored text
                oldest = datetime.fromisoformat(oldest)
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=UTC)
            age = max(0.0, (self._clock.now() - oldest).total_seconds())
        OUTBOX_PENDING.labels(outbox=t.name).set(pending)
        OUTBOX_OLDEST_AGE.labels(outbox=t.name).set(age or 0.0)
        return Backlog(pending=pending, oldest_age_seconds=age)

    async def aclose(self) -> None:
        """Stop polling and make a last delivery attempt."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        try:
            await self.flush()
        except Exception as exc:  # noqa: BLE001 — shutdown must continue; entries stay for next start
            logger.warning(
                "audit.outbox.final_flush_failed", table=self._table.name, error=str(exc)
            )

    async def _run(self) -> None:
        while True:
            try:
                await self.flush()
                await self.backlog()
            except Exception as exc:  # noqa: BLE001 — a background worker must not die
                logger.error("audit.outbox.relay_error", table=self._table.name, error=str(exc))
            await asyncio.sleep(self._poll_interval)

    async def _pending(self) -> list[RowMapping]:
        t = self._table
        async with self._db.transaction(read_only=True) as conn:
            result = await conn.execute(select(t).order_by(t.c.seq).limit(self._batch_size))
            return list(result.mappings().all())


def _to_record(row: RowMapping) -> AuditRecord:
    return AuditRecord(
        id=row["id"],
        operation=row["operation"],
        outcome=AuditOutcome(row["outcome"]),
        resource_id=row["resource_id"],
        actor=Actor(
            user_id=row["user_id"],
            correlation_id=row["correlation_id"],
            client_address=row["client_address"],
            entrypoint=row["entrypoint"],
        ),
        details=dict(row["details"]),
        occurred_at=row["occurred_at"],
    )
