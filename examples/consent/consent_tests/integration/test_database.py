"""Outages become StorageUnavailableError fast; SQL bugs propagate."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from consent_app.adapters.sql.database import Database
from consent_app.ports import StorageUnavailableError


async def test_an_unreachable_postgres_fails_fast() -> None:
    async with asyncio.timeout(5):
        with pytest.raises(StorageUnavailableError):
            await Database.connect(
                "postgresql+asyncpg://user:secret@127.0.0.1:1/consent", connect_timeout_s=0.5
            )


async def test_an_unopenable_sqlite_file_is_unavailable() -> None:
    with pytest.raises(StorageUnavailableError):
        await Database.connect("sqlite+aiosqlite:////nonexistent-dir/consent.db")


async def test_sql_bugs_propagate(database_url: str) -> None:
    db = await Database.connect(database_url)

    async def bad_query() -> None:
        async with db.transaction(read_only=True) as conn:
            await conn.execute(text("SELECT * FROM missing"))

    with pytest.raises(OperationalError, match="no such table"):
        await bad_query()
    await db.close()


async def test_a_closed_database_is_unavailable(database_url: str) -> None:
    db = await Database.connect(database_url)
    await db.close()

    assert await db.ping() is False
