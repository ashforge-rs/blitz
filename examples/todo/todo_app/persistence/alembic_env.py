"""The body of every context's Alembic ``env.py``.

Run by :meth:`ContextMigrations.upgrade` with the app's connection, or by the
``alembic`` CLI (``alembic -c todo_app/<context>/adapters/migrations/alembic.ini
revision --autogenerate -m ...``), which connects with ``TODO_DATABASE_URL``.
Not exported from ``todo_app.persistence``: it is meant to run inside Alembic.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Literal

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from todo_app.settings import TodoSettings

from .types import UtcDateTime

if TYPE_CHECKING:
    from alembic.autogenerate.api import AutogenContext
    from sqlalchemy import Connection, MetaData


def run_env(metadata: MetaData, version_table: str) -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _migrate(connection, metadata, version_table)
    else:
        asyncio.run(_migrate_standalone(metadata, version_table))


def _render_item(kind: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Autogenerate the storage type, not the app's wrapper: migrations must not import app code."""
    if kind == "type" and isinstance(obj, UtcDateTime):
        autogen_context.imports.add("import sqlalchemy as sa")
        return "sa.DateTime(timezone=True)"
    return False


def _migrate(connection: Connection, metadata: MetaData, version_table: str) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        version_table=version_table,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite can't ALTER much
        compare_type=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _migrate_standalone(metadata: MetaData, version_table: str) -> None:
    engine = create_async_engine(TodoSettings().DATABASE_URL.get_secret_value())
    async with engine.begin() as conn:
        await conn.run_sync(_migrate, metadata, version_table)
    await engine.dispose()
