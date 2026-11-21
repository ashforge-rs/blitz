"""Run a context's Alembic migrations on a :class:`Database`.

Each context has its own migration environment and version table, so the
contexts can be migrated (and one day deployed) independently.
"""

from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy import Connection

    from .database import Database


def alembic_config(script_location: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(script_location))
    return config


async def upgrade(db: Database, script_location: Path, revision: str = "head") -> None:
    """Upgrade to ``revision`` in one transaction (DDL is transactional on SQLite and Postgres)."""
    config = alembic_config(script_location)

    def _run(connection: Connection) -> None:
        # env.py uses this connection instead of opening its own.
        config.attributes["connection"] = connection
        command.upgrade(config, revision)

    async with db.transaction() as conn:
        await conn.run_sync(_run)


class SchemaOutOfDateError(RuntimeError):
    """The database schema is not at the revision this code expects."""


async def ensure_at_head(db: Database, script_location: Path, version_table: str) -> None:
    """Fail fast at startup instead of on the first query against a stale schema."""
    head = ScriptDirectory.from_config(alembic_config(script_location)).get_current_head()

    def _current(connection: Connection) -> str | None:
        context = MigrationContext.configure(connection, opts={"version_table": version_table})
        return context.get_current_revision()

    async with db.transaction(read_only=True) as conn:
        current = await conn.run_sync(_current)
    if current != head:
        msg = (
            f"schema in {version_table!r} is at {current or 'nothing'}, the code expects {head}: "
            "run `todo db upgrade` (or set TODO_DB_MIGRATE_ON_STARTUP=true)"
        )
        raise SchemaOutOfDateError(msg)
