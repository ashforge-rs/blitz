from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todo_app.todos.entities import Todo


class TodoRepository(ABC):
    @abstractmethod
    async def add(self, todo: Todo) -> None: ...

    @abstractmethod
    async def get(self, todo_id: str) -> Todo | None: ...
