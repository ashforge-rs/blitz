"""Migrations: each context's history builds exactly its tables, on every SQL backend."""

from types import ModuleType

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, MetaData, inspect

from todo_app.persistence import Database, alembic_config
from todo_app.todos.adapters import sql_migrations as todos_migrations
from todo_app.todos.adapters.sql_tables import metadata as todos_metadata
from todo_app.users.adapters import sql_migrations as users_migrations
from todo_app.users.adapters.sql_tables import metadata as users_metadata

CONTEXTS = [
    pytest.param(users_migrations, users_metadata, id="users"),
    pytest.param(todos_migrations, todos_metadata, id="todos"),
]


@pytest.fixture
async def empty_db(backend_url: str) -> Database:
    return await Database.connect(backend_url)


@pytest.mark.parametrize(("migrations", "metadata"), CONTEXTS)
async def test_migrations_at_head_match_the_table_definitions(
    empty_db: Database, migrations: ModuleType, metadata: MetaData
) -> None:
    await migrations.upgrade(empty_db)

    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "version_table": migrations.VERSION_TABLE}
        )
        return list(compare_metadata(context, metadata))

    async with empty_db.transaction(read_only=True) as conn:
        drift = await conn.run_sync(diff)
    await empty_db.close()

    assert drift == [], "sql_tables.py and migrations/ disagree: add a migration"


async def test_each_context_keeps_its_own_version_table(empty_db: Database) -> None:
    await users_migrations.upgrade(empty_db)
    await todos_migrations.upgrade(empty_db)

    async with empty_db.transaction(read_only=True) as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    await empty_db.close()

    assert {"alembic_version_users", "alembic_version_todos"} <= tables


@pytest.mark.parametrize(("migrations", "metadata"), CONTEXTS)
async def test_downgrade_to_base_and_back_up(
    empty_db: Database, migrations: ModuleType, metadata: MetaData
) -> None:
    await migrations.upgrade(empty_db)
    config = alembic_config(migrations.SCRIPT_LOCATION)

    def downgrade(connection: Connection) -> None:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")

    async with empty_db.transaction() as conn:
        await conn.run_sync(downgrade)
    async with empty_db.transaction(read_only=True) as conn:
        left = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert left.isdisjoint(metadata.tables)

    await migrations.upgrade(empty_db)  # and the history replays cleanly
    await empty_db.close()


async def test_migrations_are_idempotent(empty_db: Database) -> None:
    for _ in range(2):
        await users_migrations.upgrade(empty_db)
    await empty_db.close()
