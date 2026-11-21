import asyncio
import contextlib
import functools
import json
from datetime import datetime
from typing import TYPE_CHECKING

from audit.backend import AuditEvent, AuditEventType, AuditResult, AuditSeverity
from loguru import logger

from todo_app.kernel import Actor, AuditOutcome, AuditRecord

from .sqlite_audit_outbox import checked_table

if TYPE_CHECKING:
    import sqlite3

    from audit.backend import AuditBackend, AuditIntegrity

    from .database import Database


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
    backend outage delays delivery but never loses an entry; a crash right after
    delivery can repeat one (``metadata["audit_id"]`` identifies duplicates).
    """

    def __init__(
        self,
        db: Database,
        table: str,
        backend: AuditBackend,
        integrity: AuditIntegrity,
        *,
        poll_interval: float = 0.5,
        batch_size: int = 100,
    ) -> None:
        self._db = db
        self._table = checked_table(table)
        self._backend = backend
        self._integrity = integrity
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._flush_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"outbox-relay:{self._table}")

    async def flush(self) -> int:
        """Deliver pending entries now; returns how many were delivered."""
        async with self._flush_lock:
            delivered = 0
            while batch := await self._db.query(self._select_batch):
                for seq, record in batch:
                    event = to_audit_event(record)
                    self._integrity.add_integrity(event)
                    try:
                        await self._backend.log(event)
                    except Exception as exc:  # noqa: BLE001 — keep the entry; retry next cycle
                        logger.warning(
                            "audit.outbox.delivery_failed", table=self._table, error=str(exc)
                        )
                        return delivered
                    async with self._db.transaction() as tx:
                        await tx.execute(functools.partial(self._delete, seq=seq))
                    delivered += 1
            return delivered

    async def aclose(self) -> None:
        """Stop polling and make a last delivery attempt."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        try:
            await self.flush()
        except Exception as exc:  # noqa: BLE001 — shutdown must continue; entries stay for next start
            logger.warning("audit.outbox.final_flush_failed", table=self._table, error=str(exc))

    async def _run(self) -> None:
        while True:
            try:
                await self.flush()
            except Exception as exc:  # noqa: BLE001 — a background worker must not die
                logger.error("audit.outbox.relay_error", table=self._table, error=str(exc))
            await asyncio.sleep(self._poll_interval)

    def _delete(self, conn: sqlite3.Connection, seq: int) -> None:
        conn.execute(f"DELETE FROM {self._table} WHERE seq = ?", (seq,))  # noqa: S608 — checked identifier

    def _select_batch(self, conn: sqlite3.Connection) -> list[tuple[int, AuditRecord]]:
        rows = conn.execute(
            f"SELECT * FROM {self._table} ORDER BY seq LIMIT ?",  # noqa: S608 — checked identifier
            (self._batch_size,),
        ).fetchall()
        return [(row["seq"], _to_record(row)) for row in rows]


def _to_record(row: sqlite3.Row) -> AuditRecord:
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
        details=json.loads(row["details"]),
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
    )
