"""Migrations for the consent store (``migrations/``, version table ``alembic_version_consent``)."""

from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

if TYPE_CHECKING:
    from sqlalchemy import Connection

    from .database import Database

SCRIPT_LOCATION = Path(__file__).parent / "migrations"
VERSION_TABLE = "alembic_version_consent"


class SchemaOutOfDateError(RuntimeError):
    """The database schema is not at the revision this code expects."""


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    return config


async def upgrade(db: Database, revision: str = "head") -> None:
    config = alembic_config()

    def _run(connection: Connection) -> None:
        config.attributes["connection"] = connection  # env.py uses it, not its own
        command.upgrade(config, revision)

    async with db.transaction() as conn:
        await conn.run_sync(_run)


async def ensure_at_head(db: Database) -> None:
    """Fail fast at startup instead of on the first query against a stale schema."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()

    def _current(connection: Connection) -> str | None:
        opts = {"version_table": VERSION_TABLE}
        return MigrationContext.configure(connection, opts=opts).get_current_revision()

    async with db.transaction(read_only=True) as conn:
        current = await conn.run_sync(_current)
    if current != head:
        msg = (
            f"consent schema is at {current or 'nothing'}, the code expects {head}: "
            "run `make migrate` (or set CONSENT_DB_MIGRATE_ON_STARTUP=true)"
        )
        raise SchemaOutOfDateError(msg)
