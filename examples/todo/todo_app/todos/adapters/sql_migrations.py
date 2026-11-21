"""The todos context's Alembic environment: ``migrations/``, table ``alembic_version_todos``."""

from pathlib import Path
from typing import TYPE_CHECKING

from todo_app.persistence import ensure_at_head as _ensure_at_head
from todo_app.persistence import upgrade as _upgrade

if TYPE_CHECKING:
    from todo_app.persistence import Database

SCRIPT_LOCATION = Path(__file__).parent / "migrations"
VERSION_TABLE = "alembic_version_todos"


async def upgrade(db: Database, revision: str = "head") -> None:
    await _upgrade(db, SCRIPT_LOCATION, revision)


async def ensure_at_head(db: Database) -> None:
    await _ensure_at_head(db, SCRIPT_LOCATION, VERSION_TABLE)
