from typing import TYPE_CHECKING, Self

from consent_app.ports import ConsentUnitOfWork, ConsentUnitOfWorkFactory

from .consent_ledger import SqlConsentLedger
from .purpose_repository import SqlPurposeRepository

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncConnection

    from .database import Database


class SqlConsentUnitOfWork(ConsentUnitOfWork):
    """:class:`~consent_app.ports.ConsentUnitOfWork` as one database transaction."""

    def __init__(self, db: Database, *, read_only: bool) -> None:
        self._db = db
        self._read_only = read_only
        self._transaction: AbstractAsyncContextManager[AsyncConnection] | None = None
        self._conn: AsyncConnection | None = None

    @property
    def purposes(self) -> SqlPurposeRepository:
        return SqlPurposeRepository(self._connection())

    @property
    def ledger(self) -> SqlConsentLedger:
        return SqlConsentLedger(self._connection())

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


class SqlConsentUnitOfWorkFactory(ConsentUnitOfWorkFactory):
    def __init__(self, db: Database) -> None:
        self._db = db

    def __call__(self, *, read_only: bool = False) -> SqlConsentUnitOfWork:
        return SqlConsentUnitOfWork(self._db, read_only=read_only)
