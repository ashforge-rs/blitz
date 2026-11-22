from typing import TYPE_CHECKING

from todo_app.kernel import AuditTrail

if TYPE_CHECKING:
    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection

    from todo_app.kernel import AuditRecord


class SqlAuditOutbox(AuditTrail):
    """:class:`~todo_app.kernel.AuditTrail` that writes into the current transaction.

    The entry commits or rolls back with the business change it describes;
    :class:`~todo_app.persistence.OutboxRelay` delivers it to the audit backend.
    """

    def __init__(self, conn: AsyncConnection, table: Table) -> None:
        self._conn = conn
        self._table = table

    async def record(self, entry: AuditRecord) -> None:
        await self._conn.execute(
            self._table.insert().values(
                id=entry.id,
                operation=entry.operation,
                outcome=entry.outcome.value,
                resource_id=entry.resource_id,
                user_id=entry.actor.user_id,
                correlation_id=entry.actor.correlation_id,
                client_address=entry.actor.client_address,
                entrypoint=entry.actor.entrypoint,
                details=dict(entry.details),
                occurred_at=entry.occurred_at,
            )
        )
