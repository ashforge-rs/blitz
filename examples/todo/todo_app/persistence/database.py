import contextlib
from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from todo_app.kernel import StorageUnavailableError

from .errors import translate_storage_errors

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class Database:
    """An async SQLAlchemy engine with the transaction semantics the units of work need.

    - :meth:`transaction` is one database transaction on its own pooled
      connection: committed when the block completes, rolled back when it
      raises or is cancelled.  ``read_only=True`` always rolls back.
    - Errors follow ``persistence.errors``: outages become
      ``StorageUnavailableError``; constraint violations and SQL errors propagate.
    - SQLite: writes take the write lock up front (``BEGIN IMMEDIATE``), so two
      connections can't deadlock upgrading read locks.  Foreign keys are on and
      the journal is WAL.  Postgres: read-only transactions are ``READ ONLY``.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._closed = False

    @classmethod
    async def connect(
        cls, url: str, *, busy_timeout_ms: int = 5_000, connect_timeout_s: float = 5.0
    ) -> Self:
        """Create the engine and check the database answers.

        ``connect_timeout_s`` bounds both opening a connection and waiting for a
        free one in the pool: an unreachable database fails fast as
        ``StorageUnavailableError`` instead of hanging each request.
        """
        if url.startswith("sqlite"):
            engine = create_async_engine(url)
            _configure_sqlite(engine, busy_timeout_ms)
        else:
            engine = create_async_engine(
                url,
                connect_args={"timeout": connect_timeout_s},
                pool_timeout=connect_timeout_s,
                pool_pre_ping=True,  # a connection the server dropped is replaced, not used
            )
        db = cls(engine)
        try:
            async with db.transaction(read_only=True) as conn:
                await conn.execute(text("SELECT 1"))
        except BaseException:
            await engine.dispose()
            raise
        return db

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

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

    async def close(self) -> None:
        self._closed = True
        await self._engine.dispose()


def _configure_sqlite(engine: AsyncEngine, busy_timeout_ms: int) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        # No implicit transactions from the driver: the "begin" hook below decides.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(conn: Any) -> None:
        read_only = conn.get_execution_options().get("read_only", False)
        conn.exec_driver_sql("BEGIN" if read_only else "BEGIN IMMEDIATE")
