import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, Self

import aiosqlite
from sqlalchemy import Delete, Insert, Update, event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from consent_app.ports import ReadOnlyUnitOfWorkError, StorageUnavailableError

from .errors import translate_storage_errors

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class Database:
    """An async SQLAlchemy engine; :meth:`transaction` is one transaction on a pooled connection.

    Committed when the block completes, rolled back when it raises or is cancelled;
    ``read_only=True`` always rolls back.  SQLite writes take the write lock up
    front (``BEGIN IMMEDIATE``).  Postgres connections time out instead of hanging.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._closed = False

    @classmethod
    async def connect(cls, url: str, *, connect_timeout_s: float = 5.0) -> Self:
        if url.startswith("sqlite"):
            engine = _sqlite_engine(url)
            _configure_sqlite(engine)
        else:
            engine = create_async_engine(
                url,
                connect_args={"timeout": connect_timeout_s},
                pool_timeout=connect_timeout_s,
                pool_pre_ping=True,
            )
        _refuse_writes_when_read_only(engine)
        db = cls(engine)
        try:
            async with db.transaction(read_only=True) as conn:
                await conn.execute(text("SELECT 1"))
        except BaseException:
            await engine.dispose()
            raise
        return db

    @contextlib.asynccontextmanager
    async def transaction(self, *, read_only: bool = False) -> AsyncIterator[AsyncConnection]:
        if self._closed:
            msg = "database is closed"
            raise StorageUnavailableError(msg)
        with translate_storage_errors():
            async with self._engine.connect() as conn:
                if read_only:
                    await conn.execution_options(read_only=True, postgresql_readonly=True)
                async with conn.begin():
                    yield conn
                    if read_only:
                        await conn.rollback()

    async def ping(self) -> bool:
        try:
            async with self.transaction(read_only=True) as conn:
                await conn.execute(text("SELECT 1"))
        except StorageUnavailableError:
            return False
        return True

    async def close(self) -> None:
        self._closed = True
        await self._engine.dispose()


def _refuse_writes_when_read_only(engine: AsyncEngine) -> None:
    """One rule on every dialect (Postgres would refuse anyway; SQLite would drop silently)."""

    @event.listens_for(engine.sync_engine, "before_execute")
    def _check(conn: Any, clause: Any, *_args: Any) -> None:
        if conn.get_execution_options().get("read_only") and isinstance(
            clause, Insert | Update | Delete
        ):
            msg = "write attempted in a read-only unit of work"
            raise ReadOnlyUnitOfWorkError(msg)


def _configure_sqlite(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None  # the "begin" hook decides
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(conn: Any) -> None:
        read_only = conn.get_execution_options().get("read_only", False)
        conn.exec_driver_sql("BEGIN" if read_only else "BEGIN IMMEDIATE")


def _sqlite_engine(url: str) -> AsyncEngine:
    """An aiosqlite engine whose failed connects finish before the error propagates.

    When opening fails, aiosqlite (0.22) stops its worker thread without awaiting
    it; the thread then reports to the event loop. If the loop has closed by then
    (``asyncio.run()`` returning the error, e.g. a CLI command), the thread raises
    ``RuntimeError: Event loop is closed``. Opening connections here lets a failed
    connect wait for that thread while the loop still runs.
    """
    connect_args: tuple[list[Any], dict[str, Any]] = ([], {})

    async def open_connection() -> aiosqlite.Connection:
        cargs, cparams = connect_args
        connection = aiosqlite.connect(*cargs, **cparams)
        # `_thread` is private: if a later aiosqlite drops it, this is a plain connect.
        thread = getattr(connection, "_thread", None)
        if thread is not None:
            thread.daemon = True  # as SQLAlchemy's own aiosqlite connect does
        try:
            return await connection
        except BaseException:
            if thread is not None and thread.is_alive():
                await asyncio.to_thread(thread.join, 5)
            raise

    engine = create_async_engine(url, async_creator=open_connection)
    cargs, cparams = engine.dialect.create_connect_args(engine.url)
    connect_args[0].extend(cargs)
    connect_args[1].update(cparams)
    return engine
