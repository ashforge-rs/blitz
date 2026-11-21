from typing import TYPE_CHECKING

from sqlalchemy import select

from todo_app.todos.entities import Title, Todo
from todo_app.todos.ports import TodoRepository

from .sql_tables import todos

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


class SqlTodoRepository(TodoRepository):
    """:class:`~todo_app.todos.ports.TodoRepository` inside a unit of work's transaction."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, todo: Todo) -> None:
        await self._conn.execute(
            todos.insert().values(
                id=todo.id,
                owner_id=todo.owner_id,
                title=todo.title.value,
                done=todo.done,
                created_at=todo.created_at,
            )
        )

    async def get(self, todo_id: str) -> Todo | None:
        row = (await self._conn.execute(select(todos).where(todos.c.id == todo_id))).mappings()
        found = row.first()
        if found is None:
            return None
        return Todo(
            id=found["id"],
            owner_id=found["owner_id"],
            title=Title(found["title"]),
            done=found["done"],
            created_at=found["created_at"],
        )
