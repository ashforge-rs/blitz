from typing import TYPE_CHECKING, Self

from todo_app.persistence import (
    SqliteAuditOutbox,
    SqliteIdempotencyStore,
    idempotency_migrations,
    outbox_migrations,
)
from todo_app.todos.ports import TodosUnitOfWork, TodosUnitOfWorkFactory

from . import sqlite_todo_repository
from .sqlite_todo_repository import SqliteTodoRepository

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from todo_app.persistence import Database, Transaction

OUTBOX_TABLE = "todos_audit_outbox"
IDEMPOTENCY_TABLE = "todos_idempotency"

#: Every table the todos context owns, applied by bootstrap() on each start.
MIGRATIONS = (
    *sqlite_todo_repository.SCHEMA,
    *outbox_migrations(OUTBOX_TABLE),
    *idempotency_migrations(IDEMPOTENCY_TABLE),
)


class SqliteTodosUnitOfWork(TodosUnitOfWork):
    """:class:`~todo_app.todos.ports.TodosUnitOfWork` as one SQLite transaction.

    The repositories are bound to the open transaction; touching one outside
    ``async with`` raises instead of silently writing outside a unit of work.
    """

    def __init__(self, db: Database, *, read_only: bool) -> None:
        self._db = db
        self._read_only = read_only
        self._transaction: AbstractAsyncContextManager[Transaction] | None = None
        self._tx: Transaction | None = None

    @property
    def todos(self) -> SqliteTodoRepository:
        return SqliteTodoRepository(self._open())

    @property
    def audit(self) -> SqliteAuditOutbox:
        return SqliteAuditOutbox(self._open(), OUTBOX_TABLE)

    @property
    def idempotency(self) -> SqliteIdempotencyStore:
        return SqliteIdempotencyStore(self._open(), IDEMPOTENCY_TABLE)

    async def __aenter__(self) -> Self:
        self._transaction = self._db.transaction(write=not self._read_only)
        self._tx = await self._transaction.__aenter__()
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
            self._tx = None

    def _open(self) -> Transaction:
        if self._tx is None:
            msg = "unit of work is not open: use `async with factory() as uow:`"
            raise RuntimeError(msg)
        return self._tx


class SqliteTodosUnitOfWorkFactory(TodosUnitOfWorkFactory):
    def __init__(self, db: Database) -> None:
        self._db = db

    def __call__(self, *, read_only: bool = False) -> SqliteTodosUnitOfWork:
        return SqliteTodosUnitOfWork(self._db, read_only=read_only)
