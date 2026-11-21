"""Alembic environment for the todos context.

Run by ``todo_app.persistence.upgrade`` with the app's connection, or by the
``alembic`` CLI (``alembic -c todo_app/todos/adapters/migrations/alembic.ini
revision --autogenerate -m ...``), which connects with ``TODO_DATABASE_URL``.
"""

import asyncio
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from todo_app.persistence import UtcDateTime
from todo_app.settings import TodoSettings
from todo_app.todos.adapters.sql_migrations import VERSION_TABLE
from todo_app.todos.adapters.sql_tables import metadata


def render_item(kind: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Autogenerate the storage type, not the app's wrapper: migrations must not import app code."""
    if kind == "type" and isinstance(obj, UtcDateTime):
        autogen_context.imports.add("import sqlalchemy as sa")
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        version_table=VERSION_TABLE,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite can't ALTER much
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_standalone() -> None:
    engine = create_async_engine(TodoSettings().DATABASE_URL.get_secret_value())
    async with engine.begin() as conn:
        await conn.run_sync(run_migrations)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    asyncio.run(_run_standalone())
