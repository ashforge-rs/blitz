"""Shared fixtures.  This file sits at the example root so pytest puts it on sys.path."""

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import REGISTRY

from config import Settings
from todo_app.factory import create_todo_app
from todo_app.persistence import Database
from todo_app.settings import TodoSettings
from todo_app.todos.adapters.sqlite_todos_unit_of_work import MIGRATIONS as TODO_MIGRATIONS
from todo_app.todos.container import TodosDomain
from todo_app.users.adapters.sqlite_users_unit_of_work import MIGRATIONS as USER_MIGRATIONS
from todo_app.users.container import UsersDomain
from todo_tests.fakes import RecordingAuditBackend
from todo_tests.fixture_types import Metric, RegisterUser

# --- App + HTTP --------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "todo.db")


@pytest.fixture
def audit_log() -> RecordingAuditBackend:
    """Every audit event the app delivered.  Call ``flush_audit`` first: delivery is async."""
    return RecordingAuditBackend()


@pytest.fixture
def app(db_path: str, audit_log: RecordingAuditBackend) -> FastAPI:
    # _env_file=None: a developer's .env is never read, so tests don't depend on it.
    settings = Settings(  # type: ignore[call-arg]  # pydantic-settings init kwarg
        _env_file=None, ENVIRONMENT="test", LOG_LEVEL="WARNING", RATE_LIMIT="1000/minute"
    )
    todo_settings = TodoSettings(  # type: ignore[call-arg]  # same
        _env_file=None,
        DB_PATH=db_path,
        # The relay effectively never polls; tests deliver with ``flush_audit``.
        OUTBOX_POLL_INTERVAL_SECONDS=3600,
    )
    return create_todo_app(settings=settings, todo_settings=todo_settings, audit_backend=audit_log)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # The lifespan runs each domain's bootstrap(); without it nothing is wired.
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
def flush_audit(app: FastAPI, client: AsyncClient) -> Callable[[], Awaitable[None]]:
    """``await flush_audit()``: deliver every pending outbox entry now."""

    async def _flush() -> None:
        for kind in (UsersDomain, TodosDomain):
            await app.state.domains_by_type[kind].relay.flush()

    return _flush


@pytest.fixture
def register_user(client: AsyncClient) -> RegisterUser:
    async def _register(
        email: str = "ada@example.com", name: str = "Ada", **headers: str
    ) -> dict[str, Any]:
        r = await client.post("/v1/users/", json={"email": email, "name": name}, headers=headers)
        assert r.status_code == 201, r.text
        body: dict[str, Any] = r.json()
        return body

    return _register


# --- Infrastructure ----------------------------------------------------------


@pytest.fixture
async def db(db_path: str) -> AsyncIterator[Database]:
    """Both contexts' schemas on a fresh file, for SQLite adapter tests."""
    database = await Database.connect(db_path, migrations=USER_MIGRATIONS + TODO_MIGRATIONS)
    yield database
    await database.close()


@pytest.fixture
def metric() -> Metric:
    """``metric("todoapp_todos_created_total", result="success")`` → current value (0 if unset)."""

    def _value(name: str, **labels: str) -> float:
        return REGISTRY.get_sample_value(name, labels) or 0.0

    return _value
