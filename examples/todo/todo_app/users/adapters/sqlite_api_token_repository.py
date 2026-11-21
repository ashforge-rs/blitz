from typing import TYPE_CHECKING

from todo_app.users.ports import ApiTokenRepository

if TYPE_CHECKING:
    import sqlite3
    from datetime import datetime

    from todo_app.persistence import Transaction

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS api_tokens (
        token_hash TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        created_at TEXT NOT NULL
    ) STRICT
    """,
    "CREATE INDEX IF NOT EXISTS api_tokens_user_id ON api_tokens (user_id)",
)


class SqliteApiTokenRepository(ApiTokenRepository):
    """:class:`~todo_app.users.ports.ApiTokenRepository` inside a unit of work's transaction."""

    def __init__(self, tx: Transaction) -> None:
        self._tx = tx

    async def add(self, token_hash: str, user_id: str, created_at: datetime) -> None:
        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO api_tokens (token_hash, user_id, created_at) VALUES (?, ?, ?)",
                (token_hash, user_id, created_at.isoformat()),
            )

        await self._tx.execute(_insert)

    async def revoke(self, token_hash: str) -> None:
        def _delete(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM api_tokens WHERE token_hash = ?", (token_hash,))

        await self._tx.execute(_delete)
