from typing import TYPE_CHECKING

from todo_app.todos.ports import TodoTelemetry
from todo_app.users.ports import UserTelemetry

if TYPE_CHECKING:
    from todo_app.kernel import Actor, StorageUnavailableError
    from todo_app.todos.entities import Todo
    from todo_app.todos.use_cases import TodoErrorCode
    from todo_app.users.entities import User
    from todo_app.users.use_cases import UserErrorCode


class UserTelemetryRecorder(UserTelemetry):
    """Implements ``UserTelemetry`` by recording every call."""

    def __init__(self) -> None:
        self.registrations: list[tuple[User, bool]] = []  # (user, replayed)
        self.rejections: list[UserErrorCode] = []
        self.storage_failures: list[tuple[str, StorageUnavailableError]] = []

    async def registered(self, user: User, actor: Actor, *, replayed: bool) -> None:
        self.registrations.append((user, replayed))

    async def registration_rejected(self, reason: UserErrorCode, actor: Actor) -> None:
        self.rejections.append(reason)

    async def storage_failed(
        self, operation: str, error: StorageUnavailableError, actor: Actor
    ) -> None:
        self.storage_failures.append((operation, error))


class TodoTelemetryRecorder(TodoTelemetry):
    """Implements ``TodoTelemetry`` by recording every call."""

    def __init__(self) -> None:
        self.creations: list[tuple[Todo, bool]] = []  # (todo, replayed)
        self.rejections: list[TodoErrorCode] = []
        self.storage_failures: list[tuple[str, StorageUnavailableError]] = []

    async def created(self, todo: Todo, actor: Actor, *, replayed: bool) -> None:
        self.creations.append((todo, replayed))

    async def rejected(self, reason: TodoErrorCode, actor: Actor) -> None:
        self.rejections.append(reason)

    async def storage_failed(
        self, operation: str, error: StorageUnavailableError, actor: Actor
    ) -> None:
        self.storage_failures.append((operation, error))
