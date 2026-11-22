"""The migration history builds exactly the declared tables, on every SQL backend."""

from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect

from consent_app.adapters.sql import schema
from consent_app.adapters.sql.database import Database
from consent_app.adapters.sql.tables import metadata


@pytest.fixture
async def empty_db(backend_url: str) -> AsyncIterator[Database]:
    db = await Database.connect(backend_url)
    yield db
    await db.close()


async def test_migrations_at_head_match_the_table_definitions(empty_db: Database) -> None:
    await schema.upgrade(empty_db)

    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "version_table": schema.VERSION_TABLE}
        )
        return list(compare_metadata(context, metadata))

    async with empty_db.transaction(read_only=True) as conn:
        assert await conn.run_sync(diff) == [], "tables.py and migrations/ disagree"


async def test_downgrade_to_base_and_back_up(empty_db: Database) -> None:
    await schema.upgrade(empty_db)
    config = schema.alembic_config()

    def downgrade(connection: Connection) -> None:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")

    async with empty_db.transaction() as conn:
        await conn.run_sync(downgrade)
    async with empty_db.transaction(read_only=True) as conn:
        left = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert left.isdisjoint(metadata.tables)

    await schema.upgrade(empty_db)  # the history (and the triggers) replay cleanly


async def test_a_stale_schema_is_refused(empty_db: Database) -> None:
    with pytest.raises(schema.SchemaOutOfDateError, match="make migrate"):
        await schema.ensure_at_head(empty_db)

    await schema.upgrade(empty_db)
    await schema.ensure_at_head(empty_db)
