from typing import TYPE_CHECKING

from todo_app.users.ports import ApiTokenRepository

from .sql_tables import api_tokens

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncConnection


class SqlApiTokenRepository(ApiTokenRepository):
    """:class:`~todo_app.users.ports.ApiTokenRepository` inside a unit of work's transaction."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, token_hash: str, user_id: str, created_at: datetime) -> None:
        await self._conn.execute(
            api_tokens.insert().values(
                token_hash=token_hash, user_id=user_id, created_at=created_at
            )
        )

    async def revoke(self, token_hash: str) -> None:
        await self._conn.execute(api_tokens.delete().where(api_tokens.c.token_hash == token_hash))
