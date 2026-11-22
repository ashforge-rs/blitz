"""Database: transaction semantics and the outage-vs-bug error rule, on SQLite."""

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator
from contextlib import closing
from datetime import datetime

import pytest
from sqlalchemy import Column, MetaData, String, Table, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from todo_app.kernel import ReadOnlyUnitOfWorkError, StorageUnavailableError
from todo_app.persistence import Database, UtcDateTime
from todo_tests.fakes import EPOCH

_metadata = MetaData()
_t = Table("t", _metadata, Column("k", String, primary_key=True))
_stamps = Table("stamps", _metadata, Column("at", UtcDateTime, primary_key=True))


async def _insert(conn: AsyncConnection, k: str) -> None:
    await conn.execute(_t.insert().values(k=k))


async def _keys(db: Database) -> list[str]:
    async with db.transaction(read_only=True) as conn:
        return list((await conn.execute(select(_t.c.k).order_by(_t.c.k))).scalars())


@pytest.fixture
async def db(database_url: str) -> AsyncIterator[Database]:
    database = await Database.connect(database_url)
    async with database.transaction() as conn:
        await conn.run_sync(_metadata.create_all)
    yield database
    await database.close()


async def test_a_transaction_spans_several_awaits_and_commits_once(db: Database) -> None:
    async with db.transaction() as conn:
        await _insert(conn, "a")
        await asyncio.sleep(0)
        await _insert(conn, "b")

    assert await _keys(db) == ["a", "b"]


async def test_an_error_rolls_back_the_whole_transaction(db: Database) -> None:
    async def failing_unit() -> None:
        async with db.transaction() as conn:
            await _insert(conn, "a")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await failing_unit()
    assert await _keys(db) == []


async def test_cancellation_rolls_back(db: Database) -> None:
    inside = asyncio.Event()

    async def request() -> None:
        async with db.transaction() as conn:
            await _insert(conn, "a")
            inside.set()
            await asyncio.Event().wait()  # e.g. blitz's timeout middleware cancels here

    task = asyncio.create_task(request())
    await inside.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _keys(db) == []
    async with asyncio.timeout(5), db.transaction() as conn:  # the next request is not blocked
        await _insert(conn, "b")
    assert await _keys(db) == ["b"]


async def test_concurrent_transactions_do_not_interleave(db: Database) -> None:
    async def write(k: str) -> None:
        async with db.transaction() as conn:
            await _insert(conn, f"{k}1")
            await asyncio.sleep(0)
            await _insert(conn, f"{k}2")

    await asyncio.gather(write("a"), write("b"), write("c"))

    assert await _keys(db) == ["a1", "a2", "b1", "b2", "c1", "c2"]


async def test_read_only_transactions_refuse_writes(db: Database) -> None:
    async def write_while_reading() -> None:
        async with db.transaction(read_only=True) as conn:
            await _insert(conn, "a")

    with pytest.raises(ReadOnlyUnitOfWorkError):
        await write_while_reading()
    assert await _keys(db) == []


async def test_a_locked_database_is_storage_unavailable(db_path: str, database_url: str) -> None:
    db = await Database.connect(database_url, busy_timeout_ms=0)
    async with db.transaction() as conn:
        await conn.run_sync(_metadata.create_all)
    with closing(sqlite3.connect(db_path, isolation_level=None)) as other:
        other.execute("BEGIN IMMEDIATE")  # another process holds the write lock
        with pytest.raises(StorageUnavailableError, match="locked"):
            async with db.transaction() as conn:
                await _insert(conn, "a")
        other.execute("ROLLBACK")
    await db.close()


async def test_sql_bugs_are_not_disguised_as_unavailability(db: Database) -> None:
    with pytest.raises(OperationalError, match="no such table"):
        async with db.transaction(read_only=True) as conn:
            await conn.execute(text("SELECT * FROM missing"))


async def test_constraint_violations_propagate_for_the_caller_to_translate(db: Database) -> None:
    async def duplicate() -> None:
        async with db.transaction() as conn:
            await _insert(conn, "a")
            await _insert(conn, "a")

    with pytest.raises(IntegrityError):
        await duplicate()
    assert await _keys(db) == []


async def test_a_closed_database_is_storage_unavailable(database_url: str) -> None:
    db = await Database.connect(database_url)
    await db.close()

    with pytest.raises(StorageUnavailableError, match="closed"):
        await _keys(db)


async def test_an_unreachable_postgres_fails_fast_as_storage_unavailable() -> None:
    # Nothing listens on port 1: refused or filtered, either way no server is needed.
    async with asyncio.timeout(5):  # the connect timeout, not asyncpg's 60 s default
        with pytest.raises(StorageUnavailableError):
            await Database.connect(
                "postgresql+asyncpg://user:secret@127.0.0.1:1/todo", connect_timeout_s=0.5
            )


async def test_an_unopenable_sqlite_file_is_storage_unavailable() -> None:
    with pytest.raises(StorageUnavailableError):
        await Database.connect("sqlite+aiosqlite:////nonexistent-dir/todo.db")


def test_a_failed_sqlite_connect_leaves_no_worker_thread_behind() -> None:
    """aiosqlite stops a failed connection's thread without awaiting it; Database waits for it,
    or it outlives asyncio.run() and fails with "Event loop is closed" (any later test)."""

    def workers() -> set[threading.Thread]:
        return {t for t in threading.enumerate() if "_connection_worker_thread" in t.name}

    async def connect() -> None:
        with pytest.raises(StorageUnavailableError):
            await Database.connect("sqlite+aiosqlite:////nonexistent-dir/todo.db")

    before = workers()
    for _ in range(20):
        asyncio.run(connect())
        assert not {t for t in workers() - before if t.is_alive()}


async def test_timestamps_round_trip_as_aware_utc(db: Database) -> None:
    async with db.transaction() as conn:
        await conn.execute(_stamps.insert().values(at=EPOCH))
    async with db.transaction(read_only=True) as conn:
        [stored] = (await conn.execute(select(_stamps.c.at))).scalars()

    assert stored == EPOCH
    assert stored.tzinfo is not None


async def test_naive_timestamps_are_refused(db: Database) -> None:
    with pytest.raises(Exception, match="naive datetime"):
        async with db.transaction() as conn:
            await conn.execute(_stamps.insert().values(at=datetime(2026, 1, 1)))  # noqa: DTZ001
