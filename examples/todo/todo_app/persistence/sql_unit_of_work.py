from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncConnection

    from .database import Database


class SqlUnitOfWork:
    """The transaction lifecycle shared by every context's SQL unit of work.

    A context subclasses this *and* its unit-of-work port, and exposes its
    repositories as properties built on :meth:`_connection`.  Touching one
    outside ``async with`` raises instead of writing outside a unit of work.
    """

    def __init__(self, db: Database, *, read_only: bool) -> None:
        self._db = db
        self._read_only = read_only
        self._transaction: AbstractAsyncContextManager[AsyncConnection] | None = None
        self._conn: AsyncConnection | None = None

    async def __aenter__(self) -> Self:
        self._transaction = self._db.transaction(read_only=self._read_only)
        self._conn = await self._transaction.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._transaction is None:
            msg = "unit of work was never entered"
            raise RuntimeError(msg)
        try:
            await self._transaction.__aexit__(exc_type, exc, tb)
        finally:
            self._conn = None

    def _connection(self) -> AsyncConnection:
        if self._conn is None:
            msg = "unit of work is not open: use `async with factory() as uow:`"
            raise RuntimeError(msg)
        return self._conn
