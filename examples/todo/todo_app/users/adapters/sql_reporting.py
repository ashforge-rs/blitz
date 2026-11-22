"""Business metrics for the users context, counted straight from its tables.

Plain counts need no business rules, so this read side skips the use cases and
queries the context's own tables.  Refreshed periodically by long-running
processes, so data written by any process (``make seed`` too) shows on dashboards.
"""

from typing import TYPE_CHECKING

from prometheus_client import Gauge
from sqlalchemy import func, select

from .sql_tables import api_tokens, users

if TYPE_CHECKING:
    from todo_app.persistence import Database

REGISTERED_USERS = Gauge("todoapp_registered_users", "Users stored in the users context")
ACTIVE_TOKENS = Gauge("todoapp_active_api_tokens", "API tokens that currently authenticate")


async def publish_user_metrics(db: Database) -> None:
    async with db.transaction(read_only=True) as conn:
        user_count = (await conn.execute(select(func.count()).select_from(users))).scalar_one()
        tokens = (await conn.execute(select(func.count()).select_from(api_tokens))).scalar_one()
    REGISTERED_USERS.set(user_count)
    ACTIVE_TOKENS.set(tokens)
