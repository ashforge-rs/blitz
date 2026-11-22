"""Alembic environment for the consent store.

Run by ``schema.upgrade`` with the app's connection, or by the ``alembic`` CLI
(``alembic -c consent_app/adapters/sql/migrations/alembic.ini revision
--autogenerate -m ...``), which connects with ``CONSENT_DATABASE_URL``.
"""

import asyncio
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from consent_app.adapters.sql.schema import VERSION_TABLE
from consent_app.adapters.sql.tables import metadata
from consent_app.adapters.sql.types import UtcDateTime
from consent_app.settings import ConsentSettings


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
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_standalone() -> None:
    engine = create_async_engine(ConsentSettings().DATABASE_URL.get_secret_value())
    async with engine.begin() as conn:
        await conn.run_sync(run_migrations)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    asyncio.run(_run_standalone())
