import asyncio
import sqlite3
from collections.abc import AsyncIterator
from contextlib import closing

import pytest

from todo_app.kernel import StorageUnavailableError
from todo_app.persistence import Database, Transaction

_SCHEMA = ("CREATE TABLE IF NOT EXISTS t (k TEXT PRIMARY KEY)",)


async def _insert(tx: Transaction, k: str) -> None:
    await tx.execute(lambda c: c.execute("INSERT INTO t (k) VALUES (?)", (k,)))


async def _write(db: Database, k: str) -> None:
    async with db.transaction() as tx:
        await _insert(tx, k)


async def _keys(db: Database) -> list[str]:
    rows = await db.query(lambda c: c.execute("SELECT k FROM t ORDER BY k").fetchall())
    return [r["k"] for r in rows]


@pytest.fixture
async def db(db_path: str) -> AsyncIterator[Database]:
    database = await Database.connect(db_path, migrations=_SCHEMA)
    yield database
    await database.close()


async def test_a_transaction_spans_several_awaits_and_commits_once(db: Database) -> None:
    async with db.transaction() as tx:
        await _insert(tx, "a")
        await asyncio.sleep(0)  # other tasks may run; they can't enter the transaction
        await _insert(tx, "b")

    assert await _keys(db) == ["a", "b"]


async def test_an_error_rolls_back_the_whole_transaction(db: Database) -> None:
    async def failing_unit() -> None:
        async with db.transaction() as tx:
            await _insert(tx, "a")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await failing_unit()

    assert await _keys(db) == []


async def test_cancellation_rolls_back_and_releases_the_lock(db: Database) -> None:
    inside = asyncio.Event()

    async def request() -> None:
        async with db.transaction() as tx:
            await _insert(tx, "a")
            inside.set()
            await asyncio.Event().wait()  # e.g. the timeout middleware cancels here

    task = asyncio.create_task(request())
    await inside.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _keys(db) == []
    async with asyncio.timeout(2):  # the next request is not blocked
        async with db.transaction() as tx:
            await _insert(tx, "b")
    assert await _keys(db) == ["b"]


async def test_concurrent_transactions_do_not_interleave(db: Database) -> None:
    async def write(k: str) -> None:
        async with db.transaction() as tx:
            await _insert(tx, f"{k}1")
            await asyncio.sleep(0)
            await _insert(tx, f"{k}2")

    await asyncio.gather(write("a"), write("b"), write("c"))

    assert await _keys(db) == ["a1", "a2", "b1", "b2", "c1", "c2"]


async def test_read_only_transactions_never_persist(db: Database) -> None:
    async with db.transaction(write=False) as tx:
        await _insert(tx, "a")

    assert await _keys(db) == []


async def test_a_locked_database_is_storage_unavailable(db_path: str) -> None:
    db = await Database.connect(db_path, migrations=_SCHEMA, busy_timeout_ms=0)
    with closing(sqlite3.connect(db_path, isolation_level=None)) as other:
        other.execute("BEGIN IMMEDIATE")  # another process holds the write lock
        with pytest.raises(StorageUnavailableError, match="locked"):
            await _write(db, "a")
        other.execute("ROLLBACK")
    await db.close()


async def test_sql_bugs_are_not_disguised_as_unavailability(db: Database) -> None:
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        await db.query(lambda c: c.execute("SELECT * FROM missing").fetchall())


async def test_constraint_violations_propagate_for_the_caller_to_translate(db: Database) -> None:
    async def duplicate() -> None:
        async with db.transaction() as tx:
            await _insert(tx, "a")
            await _insert(tx, "a")

    with pytest.raises(sqlite3.IntegrityError):
        await duplicate()
    assert await _keys(db) == []


async def test_a_closed_database_is_storage_unavailable(db_path: str) -> None:
    db = await Database.connect(db_path, migrations=_SCHEMA)
    await db.close()

    with pytest.raises(StorageUnavailableError, match="closed"):
        await _keys(db)


async def test_transaction_handle_is_dead_after_the_block(db: Database) -> None:
    async with db.transaction() as tx:
        pass

    with pytest.raises(RuntimeError, match="finished"):
        await _insert(tx, "a")


async def test_migrations_are_idempotent(db_path: str) -> None:
    for _ in range(2):
        db = await Database.connect(db_path, migrations=_SCHEMA)
        await db.close()


async def test_failed_migration_closes_the_connection(db_path: str) -> None:
    # pytest turns the ResourceWarning of a leaked connection into a failure.
    with pytest.raises(sqlite3.OperationalError):
        await Database.connect(db_path, migrations=("NOT SQL",))


async def test_unopenable_path_raises() -> None:
    with pytest.raises(sqlite3.OperationalError):
        await Database.connect("/nonexistent-dir/todo.db")
