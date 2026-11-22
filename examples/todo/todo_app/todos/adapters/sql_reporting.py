"""Business metrics for the todos context, counted straight from its table."""

from typing import TYPE_CHECKING

from prometheus_client import Gauge
from sqlalchemy import func, select

from .sql_tables import todos

if TYPE_CHECKING:
    from todo_app.persistence import Database

TODOS = Gauge("todoapp_todos", "Todos stored, by state", ["done"])
OWNERS = Gauge("todoapp_users_with_todos", "Distinct users who own at least one todo")


async def publish_todo_metrics(db: Database) -> None:
    async with db.transaction(read_only=True) as conn:
        rows = await conn.execute(select(todos.c.done, func.count()).group_by(todos.c.done))
        by_done: dict[bool, int] = {bool(done): int(count) for done, count in rows}
        owners = (
            await conn.execute(select(func.count(func.distinct(todos.c.owner_id))))
        ).scalar_one()
    for done in (True, False):
        TODOS.labels(done=str(done).lower()).set(by_done.get(done, 0))
    OWNERS.set(owners)
