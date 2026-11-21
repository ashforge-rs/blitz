import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Self

from todo_app.kernel import StorageUnavailableError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterable


#: SQLite result codes (and their extended variants, e.g. SQLITE_IOERR_WRITE) that mean
#: "storage can't serve this right now", as opposed to a bug or a constraint violation.
_UNAVAILABLE = (
    "SQLITE_BUSY",
    "SQLITE_LOCKED",
    "SQLITE_IOERR",
    "SQLITE_FULL",
    "SQLITE_CANTOPEN",
    "SQLITE_READONLY",
    "SQLITE_CORRUPT",
    "SQLITE_NOTADB",
    "SQLITE_PROTOCOL",
    "SQLITE_NOMEM",
    "SQLITE_INTERRUPT",
)


class Database:
    """One SQLite connection, used from async code through explicit transactions.

    ``sqlite3`` blocks, so every statement runs on a single dedicated worker
    thread: statements run in submission order and the connection never changes
    threads.  :meth:`transaction` holds a lock for its whole duration, so one
    unit of work can span several awaits without another request's statements
    landing inside it.

    Error contract: storage failures (locked, busy, disk I/O, full, closed) are
    raised as :class:`~todo_app.kernel.StorageUnavailableError`.  Everything
    else (constraint violations, SQL errors) propagates unchanged: it is for the
    caller to translate, or it is a bug.
    """

    def __init__(self, conn: sqlite3.Connection, executor: ThreadPoolExecutor) -> None:
        self._conn = conn
        self._executor = executor
        self._lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def connect(
        cls,
        path: str,
        *,
        migrations: Iterable[str] = (),
        busy_timeout_ms: int = 5_000,
    ) -> Self:
        """Open ``path``, apply ``migrations`` in one transaction and return the database.

        Migrations must be idempotent (``CREATE ... IF NOT EXISTS``); they run on
        every start.  A real project would version them (Alembic, yoyo).
        """
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlite")

        def _open() -> sqlite3.Connection:
            # isolation_level=None: no implicit transactions; we issue BEGIN/COMMIT.
            conn = sqlite3.connect(path, timeout=busy_timeout_ms / 1000, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            # WAL lets readers proceed while a write is in progress.
            conn.execute("PRAGMA journal_mode = WAL")
            return conn

        try:
            conn = await asyncio.get_running_loop().run_in_executor(executor, _open)
        except BaseException:
            executor.shutdown(wait=False)
            raise

        db = cls(conn, executor)
        try:
            async with db.transaction() as tx:
                await tx.execute(lambda conn: _apply(conn, migrations))
        except BaseException:
            await db.close()
            raise
        return db

    @asynccontextmanager
    async def transaction(self, *, write: bool = True) -> AsyncIterator[Transaction]:
        """One atomic unit of work: committed if the block completes, rolled back otherwise.

        ``write=True`` takes SQLite's write lock up front (``BEGIN IMMEDIATE``), so
        two connections can't deadlock upgrading read locks.  ``write=False``
        always ends in ``ROLLBACK``.
        """
        async with self._lock:
            await self._call(self._conn.execute, "BEGIN IMMEDIATE" if write else "BEGIN")
            tx = Transaction(self)
            try:
                yield tx
                # A read-only transaction never persists anything, even if written to.
                await self._call(self._conn.execute, "COMMIT" if write else "ROLLBACK")
            except BaseException:
                # Shielded: a cancelled request still rolls back.  The worker runs
                # jobs in order, so this lands before the next transaction's BEGIN
                # even if the shield itself is cancelled.
                await asyncio.shield(self._submit(self._rollback_if_open))
                raise
            finally:
                tx.close()

    async def query[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run a read in its own (deferred) transaction."""
        async with self.transaction(write=False) as tx:
            return await tx.execute(work)

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            await self._submit(self._conn.close)
            self._executor.shutdown(wait=False)

    async def _call[T](self, fn: Callable[..., T], *args: Any) -> T:
        if self._closed:
            msg = "database is closed"
            raise StorageUnavailableError(msg)
        try:
            return await self._submit(fn, *args)
        except sqlite3.DatabaseError as exc:
            # By SQLite result code, not exception class: OperationalError also
            # covers syntax errors and missing tables, which are bugs.
            if (getattr(exc, "sqlite_errorname", None) or "").startswith(_UNAVAILABLE):
                raise StorageUnavailableError(str(exc)) from exc
            raise

    def _submit[T](self, fn: Callable[..., T], *args: Any) -> asyncio.Future[T]:
        return asyncio.get_running_loop().run_in_executor(self._executor, fn, *args)

    def _rollback_if_open(self) -> None:
        if self._conn.in_transaction:
            self._conn.execute("ROLLBACK")


def _apply(conn: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        conn.execute(statement)


class Transaction:
    """Handle to the open transaction; valid only inside ``async with db.transaction()``."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._open = True

    async def execute[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``work(conn)`` on the database thread, inside this transaction."""
        if not self._open:
            msg = "transaction is finished"
            raise RuntimeError(msg)
        return await self._db._call(work, self._db._conn)

    def close(self) -> None:
        self._open = False
