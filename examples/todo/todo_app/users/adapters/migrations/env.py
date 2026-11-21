"""Alembic environment for the users context (see ``todo_app/persistence/alembic_env.py``)."""

from todo_app.persistence.alembic_env import run_env
from todo_app.users.adapters.sql_migrations import MIGRATIONS
from todo_app.users.adapters.sql_tables import metadata

run_env(metadata, MIGRATIONS.version_table)
