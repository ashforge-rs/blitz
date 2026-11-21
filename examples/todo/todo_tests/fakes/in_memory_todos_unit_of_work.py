from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from todo_app.todos.ports import TodoRepository, TodosUnitOfWork, TodosUnitOfWorkFactory

from .in_memory_unit_of_work import InMemoryState, InMemoryUnitOfWork, InMemoryUnitOfWorkFactory

if TYPE_CHECKING:
    from todo_app.todos.entities import Todo


@dataclass
class TodosState(InMemoryState):
    todos: dict[str, Todo] = field(default_factory=dict)


class InMemoryTodosUnitOfWorkFactory(InMemoryUnitOfWorkFactory[TodosState], TodosUnitOfWorkFactory):
    """``TodosUnitOfWorkFactory`` with real transaction semantics, in memory."""

    def __init__(self) -> None:
        super().__init__(TodosState())

    def __call__(self, *, read_only: bool = False) -> InMemoryTodosUnitOfWork:
        return InMemoryTodosUnitOfWork(self, read_only=read_only)


class InMemoryTodosUnitOfWork(InMemoryUnitOfWork[TodosState], TodosUnitOfWork):
    @property
    def todos(self) -> InMemoryTodoRepository:
        return InMemoryTodoRepository(self._work)


class InMemoryTodoRepository(TodoRepository):
    def __init__(self, state: TodosState) -> None:
        self._s = state

    async def add(self, todo: Todo) -> None:
        self._s.todos[todo.id] = todo

    async def get(self, todo_id: str) -> Todo | None:
        return self._s.todos.get(todo_id)
