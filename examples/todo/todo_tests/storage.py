"""SQL backends the storage tests run on: SQLite always, Postgres when configured.

Set ``TODO_TEST_POSTGRES_URL`` (e.g. ``postgresql+asyncpg://postgres:postgres@localhost:5432/
todo_test``) to include Postgres; CI does.  That database is wiped before each test.
"""

import os

from sqlalchemy import text

from todo_app.persistence import Database
from todo_app.todos.adapters import sql_migrations as todos_migrations
from todo_app.todos.adapters.sql_tables import metadata as todos_metadata
from todo_app.users.adapters import sql_migrations as users_migrations
from todo_app.users.adapters.sql_tables import metadata as users_metadata

POSTGRES_URL = os.environ.get("TODO_TEST_POSTGRES_URL")
BACKENDS = ["sqlite", *(["postgres"] if POSTGRES_URL else [])]


async def url_for(backend: str, sqlite_url: str) -> str:
    """The URL for ``backend``, with an empty database behind it."""
    if backend == "sqlite":
        return sqlite_url
    if POSTGRES_URL is None:
        msg = "TODO_TEST_POSTGRES_URL is not set"
        raise RuntimeError(msg)
    db = await Database.connect(POSTGRES_URL)
    async with db.transaction() as conn:
        for metadata in (users_metadata, todos_metadata):
            await conn.run_sync(metadata.drop_all)
        for version_table in (users_migrations.VERSION_TABLE, todos_migrations.VERSION_TABLE):
            await conn.execute(text(f"DROP TABLE IF EXISTS {version_table}"))
    await db.close()
    return POSTGRES_URL


async def open_migrated(url: str) -> Database:
    """Both contexts' schemas, migrated to head."""
    db = await Database.connect(url)
    await users_migrations.upgrade(db)
    await todos_migrations.upgrade(db)
    return db
