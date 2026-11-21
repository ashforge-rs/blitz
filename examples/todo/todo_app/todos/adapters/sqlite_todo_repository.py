from datetime import datetime
from typing import TYPE_CHECKING

from todo_app.todos.entities import Title, Todo
from todo_app.todos.ports import TodoRepository

if TYPE_CHECKING:
    import sqlite3

    from todo_app.persistence import Transaction

#: ``owner_id`` has no foreign key into ``users``: each context owns its tables,
#: so either can move to its own database without the other noticing.
SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS todos (
        id         TEXT PRIMARY KEY,
        owner_id   TEXT NOT NULL,
        title      TEXT NOT NULL,
        done       INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)),
        created_at TEXT NOT NULL
    ) STRICT
    """,
    "CREATE INDEX IF NOT EXISTS todos_owner_id ON todos (owner_id)",
)


class SqliteTodoRepository(TodoRepository):
    """:class:`~todo_app.todos.ports.TodoRepository` inside a unit of work's transaction."""

    def __init__(self, tx: Transaction) -> None:
        self._tx = tx

    async def add(self, todo: Todo) -> None:
        def _insert(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO todos (id, owner_id, title, done, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    todo.id,
                    todo.owner_id,
                    todo.title.value,
                    int(todo.done),
                    todo.created_at.isoformat(),
                ),
            )

        await self._tx.execute(_insert)

    async def get(self, todo_id: str) -> Todo | None:
        def _select(conn: sqlite3.Connection) -> sqlite3.Row | None:
            row: sqlite3.Row | None = conn.execute(
                "SELECT id, owner_id, title, done, created_at FROM todos WHERE id = ?", (todo_id,)
            ).fetchone()
            return row

        row = await self._tx.execute(_select)
        if row is None:
            return None
        return Todo(
            id=row["id"],
            owner_id=row["owner_id"],
            title=Title(row["title"]),
            done=bool(row["done"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
