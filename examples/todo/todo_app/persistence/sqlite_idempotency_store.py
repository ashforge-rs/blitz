from datetime import datetime
from typing import TYPE_CHECKING

from todo_app.kernel import IdempotencyRecord, IdempotencyStore

from .sqlite_audit_outbox import checked_table

if TYPE_CHECKING:
    import sqlite3

    from .database import Transaction


def idempotency_migrations(table: str) -> tuple[str, ...]:
    table = checked_table(table)
    return (
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            scope               TEXT NOT NULL,
            key                 TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            resource_id         TEXT NOT NULL,
            secret_ref          TEXT,
            created_at          TEXT NOT NULL,
            PRIMARY KEY (scope, key)
        ) STRICT
        """,
    )


class SqliteIdempotencyStore(IdempotencyStore):
    """:class:`~todo_app.kernel.IdempotencyStore` inside the current transaction."""

    def __init__(self, tx: Transaction, table: str) -> None:
        self._tx = tx
        self._table = checked_table(table)

    async def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        sql = (
            "SELECT scope, key, request_fingerprint, resource_id, secret_ref, created_at "  # noqa: S608 — checked identifier
            f"FROM {self._table} WHERE scope = ? AND key = ?"
        )

        def _select(conn: sqlite3.Connection) -> sqlite3.Row | None:
            row: sqlite3.Row | None = conn.execute(sql, (scope, key)).fetchone()
            return row

        row = await self._tx.execute(_select)
        if row is None:
            return None
        return IdempotencyRecord(
            scope=row["scope"],
            key=row["key"],
            request_fingerprint=row["request_fingerprint"],
            resource_id=row["resource_id"],
            secret_ref=row["secret_ref"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def put(self, record: IdempotencyRecord) -> None:
        sql = (
            f"INSERT INTO {self._table} (scope, key, request_fingerprint, resource_id, "  # noqa: S608 — checked identifier
            "secret_ref, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (scope, key) DO UPDATE SET "
            "request_fingerprint = excluded.request_fingerprint, "
            "resource_id = excluded.resource_id, secret_ref = excluded.secret_ref, "
            "created_at = excluded.created_at"
        )
        params = (
            record.scope,
            record.key,
            record.request_fingerprint,
            record.resource_id,
            record.secret_ref,
            record.created_at.isoformat(),
        )

        def _upsert(conn: sqlite3.Connection) -> None:
            conn.execute(sql, params)

        await self._tx.execute(_upsert)
