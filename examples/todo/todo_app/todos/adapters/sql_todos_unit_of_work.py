from todo_app.persistence import Database, SqlAuditOutbox, SqlIdempotencyStore, SqlUnitOfWork
from todo_app.todos.ports import TodosUnitOfWork, TodosUnitOfWorkFactory

from .sql_tables import audit_outbox, idempotency
from .sql_todo_repository import SqlTodoRepository


class SqlTodosUnitOfWork(SqlUnitOfWork, TodosUnitOfWork):
    """:class:`~todo_app.todos.ports.TodosUnitOfWork` as one database transaction."""

    @property
    def todos(self) -> SqlTodoRepository:
        return SqlTodoRepository(self._connection())

    @property
    def audit(self) -> SqlAuditOutbox:
        return SqlAuditOutbox(self._connection(), audit_outbox)

    @property
    def idempotency(self) -> SqlIdempotencyStore:
        return SqlIdempotencyStore(self._connection(), idempotency)


class SqlTodosUnitOfWorkFactory(TodosUnitOfWorkFactory):
    def __init__(self, db: Database) -> None:
        self._db = db

    def __call__(self, *, read_only: bool = False) -> SqlTodosUnitOfWork:
        return SqlTodosUnitOfWork(self._db, read_only=read_only)
