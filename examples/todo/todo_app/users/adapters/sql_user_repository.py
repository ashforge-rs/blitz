from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from todo_app.persistence.errors import violates_unique
from todo_app.users.entities import DisplayName, EmailAddress, User
from todo_app.users.ports import EmailTakenError, UserRepository

from .sql_tables import EMAIL_UNIQUE, api_tokens, users

if TYPE_CHECKING:
    from sqlalchemy import RowMapping
    from sqlalchemy.ext.asyncio import AsyncConnection


class SqlUserRepository(UserRepository):
    """:class:`~todo_app.users.ports.UserRepository` inside a unit of work's transaction."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, user: User) -> None:
        statement = users.insert().values(
            id=user.id, email=user.email.value, name=user.name.value, created_at=user.created_at
        )
        try:
            await self._conn.execute(statement)
        except IntegrityError as exc:
            # The constraint decides, not a SELECT first: concurrent registrations can't both win.
            if violates_unique(exc, constraint=EMAIL_UNIQUE, sqlite_columns="users.email"):
                raise EmailTakenError from exc
            raise

    async def get(self, user_id: str) -> User | None:
        row = (await self._conn.execute(select(users).where(users.c.id == user_id))).mappings()
        return _to_user(row.first())

    async def find_by_token_hash(self, token_hash: str) -> User | None:
        statement = (
            select(users)
            .join(api_tokens, api_tokens.c.user_id == users.c.id)
            .where(api_tokens.c.token_hash == token_hash)
        )
        return _to_user((await self._conn.execute(statement)).mappings().first())


def _to_user(row: RowMapping | None) -> User | None:
    if row is None:
        return None
    return User(
        id=row["id"],
        email=EmailAddress(row["email"]),
        name=DisplayName(row["name"]),
        created_at=row["created_at"],
    )
