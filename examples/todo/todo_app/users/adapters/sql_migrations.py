from pathlib import Path

from todo_app.persistence import ContextMigrations

#: The users context's Alembic history (``migrations/``), tracked in its own version table.
MIGRATIONS = ContextMigrations(
    script_location=Path(__file__).parent / "migrations",
    version_table="alembic_version_users",
)
