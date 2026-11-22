from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from types import TracebackType

    from .consent_ledger import ConsentLedger
    from .purpose_repository import PurposeRepository


class ConsentUnitOfWork(ABC):
    """One atomic change: commits when the ``async with`` block completes, rolls back if it raises.

    Raises ``StorageUnavailableError`` when storage is down.
    """

    @property
    @abstractmethod
    def purposes(self) -> PurposeRepository: ...

    @property
    @abstractmethod
    def ledger(self) -> ConsentLedger: ...

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class ConsentUnitOfWorkFactory(ABC):
    @abstractmethod
    def __call__(self, *, read_only: bool = False) -> ConsentUnitOfWork: ...
