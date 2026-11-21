"""Run a context's Alembic migrations on a :class:`Database`.

Each context has its own migration environment and version table, so the
contexts can be migrated (and one day deployed) independently.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy import Connection

    from .database import Database


class SchemaOutOfDateError(RuntimeError):
    """The database schema is not at the revision this code expects."""


def alembic_config(script_location: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(script_location))
    return config


@dataclass(frozen=True, slots=True)
class ContextMigrations:
    """One context's migration history: where it lives and which version table tracks it."""

    script_location: Path
    version_table: str

    async def upgrade(self, db: Database, revision: str = "head") -> None:
        """Upgrade in one transaction (DDL is transactional on SQLite and Postgres)."""
        config = alembic_config(self.script_location)

        def _run(connection: Connection) -> None:
            config.attributes["connection"] = connection  # env.py uses it, not its own
            command.upgrade(config, revision)

        async with db.transaction() as conn:
            await conn.run_sync(_run)

    async def ensure_at_head(self, db: Database) -> None:
        """Fail fast at startup instead of on the first query against a stale schema."""
        head = ScriptDirectory.from_config(alembic_config(self.script_location)).get_current_head()

        def _current(connection: Connection) -> str | None:
            opts = {"version_table": self.version_table}
            return MigrationContext.configure(connection, opts=opts).get_current_revision()

        async with db.transaction(read_only=True) as conn:
            current = await conn.run_sync(_current)
        if current != head:
            msg = (
                f"schema in {self.version_table!r} is at {current or 'nothing'}, the code "
                f"expects {head}: run `todo db upgrade` (or set TODO_DB_MIGRATE_ON_STARTUP=true)"
            )
            raise SchemaOutOfDateError(msg)
