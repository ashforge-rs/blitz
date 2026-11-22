from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from types import TracebackType

    from todo_app.kernel import AuditTrail, IdempotencyStore

    from .api_token_repository import ApiTokenRepository
    from .user_repository import UserRepository


class UsersUnitOfWork(ABC):
    """One atomic change: everything written through these ports commits together.

    ``async with factory() as uow:`` commits when the block completes and rolls
    back when it raises.  Raises ``StorageUnavailableError`` when storage is down.
    """

    @property
    @abstractmethod
    def users(self) -> UserRepository: ...

    @property
    @abstractmethod
    def api_tokens(self) -> ApiTokenRepository: ...

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


class UsersUnitOfWorkFactory(ABC):
    @abstractmethod
    def __call__(self, *, read_only: bool = False) -> UsersUnitOfWork: ...
