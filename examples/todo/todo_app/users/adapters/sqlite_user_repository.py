import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING

from todo_app.users.entities import DisplayName, EmailAddress, User
from todo_app.users.ports import EmailTakenError, UserRepository

if TYPE_CHECKING:
    from todo_app.persistence import Transaction

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id         TEXT PRIMARY KEY,
        email      TEXT NOT NULL UNIQUE,
        name       TEXT NOT NULL,
        created_at TEXT NOT NULL
    ) STRICT
    """,
)

_COLUMNS = "u.id, u.email, u.name, u.created_at"


class SqliteUserRepository(UserRepository):
    """:class:`~todo_app.users.ports.UserRepository` inside a unit of work's transaction."""

    def __init__(self, tx: Transaction) -> None:
        self._tx = tx

    async def add(self, user: User) -> None:
        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
                (user.id, user.email.value, user.name.value, user.created_at.isoformat()),
            )

        try:
            await self._tx.execute(_insert)
        except sqlite3.IntegrityError as exc:
            if "users.email" in str(exc):
                raise EmailTakenError from exc
            raise

    async def get(self, user_id: str) -> User | None:
        return await self._one(f"SELECT {_COLUMNS} FROM users AS u WHERE u.id = ?", user_id)  # noqa: S608 — constant column list

    async def find_by_token_hash(self, token_hash: str) -> User | None:
        return await self._one(
            f"SELECT {_COLUMNS} FROM users AS u "  # noqa: S608 — constant column list
            "JOIN api_tokens AS t ON t.user_id = u.id WHERE t.token_hash = ?",
            token_hash,
        )

    async def _one(self, sql: str, param: str) -> User | None:
        def _select(conn: sqlite3.Connection) -> sqlite3.Row | None:
            row: sqlite3.Row | None = conn.execute(sql, (param,)).fetchone()
            return row

        row = await self._tx.execute(_select)
        return None if row is None else _to_user(row)


def _to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        email=EmailAddress(row["email"]),
        name=DisplayName(row["name"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
