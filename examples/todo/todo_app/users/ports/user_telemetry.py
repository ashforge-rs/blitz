from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todo_app.kernel import Actor, StorageUnavailableError
    from todo_app.users.entities import User
    from todo_app.users.use_cases.errors import UserErrorCode


class UserTelemetry(ABC):
    """Metrics and logs for the users use cases.

    Called after the unit of work has finished, so implementations must not
    raise: a telemetry failure must never change a committed result.  (Audit
    entries are not telemetry; they are written inside the unit of work.)
    """

    @abstractmethod
    async def registered(self, user: User, actor: Actor, *, replayed: bool) -> None: ...

    @abstractmethod
    async def registration_rejected(self, reason: UserErrorCode, actor: Actor) -> None: ...

    @abstractmethod
    async def storage_failed(
        self, operation: str, error: StorageUnavailableError, actor: Actor
    ) -> None: ...
