import json
import re
from typing import TYPE_CHECKING

from todo_app.kernel import AuditTrail

if TYPE_CHECKING:
    import sqlite3

    from todo_app.kernel import AuditRecord

    from .database import Transaction

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


def checked_table(name: str) -> str:
    """Table names are interpolated into SQL, so allow identifiers only."""
    if not _IDENTIFIER.fullmatch(name):
        msg = f"invalid table name {name!r}"
        raise ValueError(msg)
    return name


def outbox_migrations(table: str) -> tuple[str, ...]:
    table = checked_table(table)
    return (
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            seq            INTEGER PRIMARY KEY AUTOINCREMENT,
            id             TEXT NOT NULL UNIQUE,
            operation      TEXT NOT NULL,
            outcome        TEXT NOT NULL,
            resource_id    TEXT,
            user_id        TEXT,
            correlation_id TEXT NOT NULL,
            client_address TEXT,
            entrypoint     TEXT,
            details        TEXT NOT NULL,
            occurred_at    TEXT NOT NULL
        ) STRICT
        """,
    )


class SqliteAuditOutbox(AuditTrail):
    """:class:`~todo_app.kernel.AuditTrail` that writes into the current transaction.

    The entry commits or rolls back with the business change it describes;
    :class:`~todo_app.persistence.OutboxRelay` delivers it to the audit backend.
    """

    def __init__(self, tx: Transaction, table: str) -> None:
        self._tx = tx
        self._table = checked_table(table)

    async def record(self, entry: AuditRecord) -> None:
        sql = (
            f"INSERT INTO {self._table} (id, operation, outcome, resource_id, user_id, "  # noqa: S608 — checked identifier
            "correlation_id, client_address, entrypoint, details, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            entry.id,
            entry.operation,
            entry.outcome.value,
            entry.resource_id,
            entry.actor.user_id,
            entry.actor.correlation_id,
            entry.actor.client_address,
            entry.actor.entrypoint,
            json.dumps(entry.details, sort_keys=True),
            entry.occurred_at.isoformat(),
        )

        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(sql, params)

        await self._tx.execute(_insert)
