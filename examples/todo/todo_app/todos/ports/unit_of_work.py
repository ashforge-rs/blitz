from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from types import TracebackType

    from todo_app.kernel import AuditTrail, IdempotencyStore

    from .todo_repository import TodoRepository


class TodosUnitOfWork(ABC):
    """One atomic change: everything written through these ports commits together.

    ``async with factory() as uow:`` commits when the block completes and rolls
    back when it raises.  Raises ``StorageUnavailableError`` when storage is down.
    """

    @property
    @abstractmethod
    def todos(self) -> TodoRepository: ...

    @property
    @abstractmethod
    def audit(self) -> AuditTrail: ...

    @property
    @abstractmethod
    def idempotency(self) -> IdempotencyStore: ...

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class TodosUnitOfWorkFactory(ABC):
    @abstractmethod
    def __call__(self, *, read_only: bool = False) -> TodosUnitOfWork: ...
