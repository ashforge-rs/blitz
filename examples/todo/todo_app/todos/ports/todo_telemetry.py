from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todo_app.kernel import Actor, StorageUnavailableError
    from todo_app.todos.entities import Todo
    from todo_app.todos.use_cases.errors import TodoErrorCode


class TodoTelemetry(ABC):
    """Metrics and logs for the todos use cases.  Must not raise (runs after commit)."""

    @abstractmethod
    async def created(self, todo: Todo, actor: Actor, *, replayed: bool) -> None: ...

    @abstractmethod
    async def rejected(self, reason: TodoErrorCode, actor: Actor) -> None: ...

    @abstractmethod
    async def storage_failed(
        self, operation: str, error: StorageUnavailableError, actor: Actor
    ) -> None: ...
