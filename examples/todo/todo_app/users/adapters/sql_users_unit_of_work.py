from todo_app.persistence import Database, SqlAuditOutbox, SqlIdempotencyStore, SqlUnitOfWork
from todo_app.users.ports import UsersUnitOfWork, UsersUnitOfWorkFactory

from .sql_api_token_repository import SqlApiTokenRepository
from .sql_tables import audit_outbox, idempotency
from .sql_user_repository import SqlUserRepository


class SqlUsersUnitOfWork(SqlUnitOfWork, UsersUnitOfWork):
    """:class:`~todo_app.users.ports.UsersUnitOfWork` as one database transaction."""

    @property
    def users(self) -> SqlUserRepository:
        return SqlUserRepository(self._connection())

    @property
    def api_tokens(self) -> SqlApiTokenRepository:
        return SqlApiTokenRepository(self._connection())

    @property
    def audit(self) -> SqlAuditOutbox:
        return SqlAuditOutbox(self._connection(), audit_outbox)

    @property
    def idempotency(self) -> SqlIdempotencyStore:
        return SqlIdempotencyStore(self._connection(), idempotency)


class SqlUsersUnitOfWorkFactory(UsersUnitOfWorkFactory):
    def __init__(self, db: Database) -> None:
        self._db = db

    def __call__(self, *, read_only: bool = False) -> SqlUsersUnitOfWork:
        return SqlUsersUnitOfWork(self._db, read_only=read_only)
