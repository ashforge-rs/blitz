from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from todo_app.kernel import IdempotencyKeyTakenError, IdempotencyRecord, IdempotencyStore

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection


class SqlIdempotencyStore(IdempotencyStore):
    """:class:`~todo_app.kernel.IdempotencyStore` inside the current transaction.

    :meth:`add` relies on the ``(scope, key)`` primary key: a concurrent request
    with the same key blocks on it, then fails with ``IdempotencyKeyTakenError``
    once the first commits, so only one of them can create anything.
    """

    def __init__(self, conn: AsyncConnection, table: Table) -> None:
        self._conn = conn
        self._table = table

    async def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        t = self._table
        row = (
            (await self._conn.execute(select(t).where(t.c.scope == scope, t.c.key == key)))
            .mappings()
            .first()
        )
        return None if row is None else IdempotencyRecord(**row)

    async def add(self, record: IdempotencyRecord) -> None:
        try:
            # A savepoint keeps the outer transaction usable after the violation
            # (Postgres aborts the whole transaction on any failed statement).
            async with self._conn.begin_nested():
                await self._conn.execute(self._table.insert().values(**_values(record)))
        except IntegrityError as exc:
            raise IdempotencyKeyTakenError from exc

    async def replace(self, record: IdempotencyRecord) -> None:
        t = self._table
        await self._conn.execute(
            t.update()
            .where(t.c.scope == record.scope, t.c.key == record.key)
            .values(**_values(record))
        )


async def purge_expired(conn: AsyncConnection, table: Table, *, created_before: datetime) -> int:
    """Delete records that can no longer be replayed; returns how many went."""
    result = await conn.execute(delete(table).where(table.c.created_at < created_before))
    return result.rowcount


def _values(record: IdempotencyRecord) -> dict[str, object]:
    return {
        "scope": record.scope,
        "key": record.key,
        "request_fingerprint": record.request_fingerprint,
        "resource_id": record.resource_id,
        "secret_ref": record.secret_ref,
        "created_at": record.created_at,
    }
