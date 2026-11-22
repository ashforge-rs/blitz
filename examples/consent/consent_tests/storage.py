"""SQL backends the storage tests run on: SQLite always, Postgres when configured.

Set ``CONSENT_TEST_POSTGRES_URL`` (e.g. ``postgresql+asyncpg://todo:todo@localhost:5432/
todo_test``) to include Postgres; CI does.  That database is wiped before each test.
"""

import os

from sqlalchemy import text

from consent_app.adapters.sql import schema
from consent_app.adapters.sql.database import Database
from consent_app.adapters.sql.tables import metadata

POSTGRES_URL = os.environ.get("CONSENT_TEST_POSTGRES_URL")
BACKENDS = ["sqlite", *(["postgres"] if POSTGRES_URL else [])]


async def url_for(backend: str, sqlite_url: str) -> str:
    if backend == "sqlite":
        return sqlite_url
    if POSTGRES_URL is None:
        msg = "CONSENT_TEST_POSTGRES_URL is not set"
        raise RuntimeError(msg)
    db = await Database.connect(POSTGRES_URL)
    async with db.transaction() as conn:
        await conn.execute(text("DROP FUNCTION IF EXISTS consent_events_append_only() CASCADE"))
        await conn.run_sync(metadata.drop_all)
        await conn.execute(text(f"DROP TABLE IF EXISTS {schema.VERSION_TABLE}"))
    await db.close()
    return POSTGRES_URL


async def open_migrated(url: str) -> Database:
    db = await Database.connect(url)
    await schema.upgrade(db)
    return db
