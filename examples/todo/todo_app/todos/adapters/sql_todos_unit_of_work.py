from typing import TYPE_CHECKING, Self

from todo_app.persistence import SqlAuditOutbox, SqlIdempotencyStore
from todo_app.todos.ports import TodosUnitOfWork, TodosUnitOfWorkFactory

from .sql_tables import audit_outbox, idempotency
from .sql_todo_repository import SqlTodoRepository

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncConnection

    from todo_app.persistence import Database


class SqlTodosUnitOfWork(TodosUnitOfWork):
    """:class:`~todo_app.todos.ports.TodosUnitOfWork` as one database transaction.

    The repositories are bound to the open transaction; touching one outside
    ``async with`` raises instead of silently writing outside a unit of work.
    """

    def __init__(self, db: Database, *, read_only: bool) -> None:
        self._db = db
        self._read_only = read_only
        self._transaction: AbstractAsyncContextManager[AsyncConnection] | None = None
        self._conn: AsyncConnection | None = None

    @property
    def todos(self) -> SqlTodoRepository:
        return SqlTodoRepository(self._open())

    @property
    def audit(self) -> SqlAuditOutbox:
        return SqlAuditOutbox(self._open(), audit_outbox)

    @property
    def idempotency(self) -> SqlIdempotencyStore:
        return SqlIdempotencyStore(self._open(), idempotency)

    async def __aenter__(self) -> Self:
        self._transaction = self._db.transaction(read_only=self._read_only)
        self._conn = await self._transaction.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._transaction is None:
            msg = "unit of work was never entered"
            raise RuntimeError(msg)
        try:
            await self._transaction.__aexit__(exc_type, exc, tb)
        finally:
            self._conn = None

    def _open(self) -> AsyncConnection:
        if self._conn is None:
            msg = "unit of work is not open: use `async with factory() as uow:`"
            raise RuntimeError(msg)
        return self._conn


class SqlTodosUnitOfWorkFactory(TodosUnitOfWorkFactory):
    def __init__(self, db: Database) -> None:
        self._db = db

    def __call__(self, *, read_only: bool = False) -> SqlTodosUnitOfWork:
        return SqlTodosUnitOfWork(self._db, read_only=read_only)
