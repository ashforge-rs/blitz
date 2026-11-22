"""After seeding, the business gauges show what the database holds."""

from collections.abc import Callable

from audit.backends.noop import NoopAuditBackend
from pydantic import SecretStr

from todo_app.cli.composition import open_services
from todo_app.cli.seed import DEMO_USERS, seed_demo_data
from todo_app.persistence import Database
from todo_app.settings import TodoSettings
from todo_app.todos.adapters.sql_reporting import publish_todo_metrics
from todo_app.users.adapters.sql_reporting import publish_user_metrics


async def test_gauges_count_the_seeded_users_and_todos(
    database_url: str, metric: Callable[..., float]
) -> None:
    settings = TodoSettings(_env_file=None, DATABASE_URL=SecretStr(database_url))  # type: ignore[call-arg]  # pydantic-settings init kwarg
    async with open_services(settings, audit_backend=NoopAuditBackend()) as services:
        report = await seed_demo_data(services, environment="development")

    db = await Database.connect(database_url)
    await publish_user_metrics(db)
    await publish_todo_metrics(db)
    await db.close()

    assert metric("todoapp_registered_users") == len(DEMO_USERS)
    assert metric("todoapp_active_api_tokens") == len(DEMO_USERS)
    assert metric("todoapp_todos", done="false") == sum(len(u.todos) for u in report.users)
    assert metric("todoapp_todos", done="true") == 0
    assert metric("todoapp_users_with_todos") == len(DEMO_USERS)
