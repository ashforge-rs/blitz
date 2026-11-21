import pytest
from httpx import AsyncClient

from todo_app.kernel import StorageUnavailableError
from todo_app.todos.adapters.sqlite_todo_repository import SqliteTodoRepository
from todo_tests.fixture_types import Metric, RegisterUser


async def test_counters_track_requests_and_are_exposed(
    client: AsyncClient, register_user: RegisterUser, metric: Metric
) -> None:
    before = {
        "registered": metric("todoapp_users_registered_total", result="success"),
        "taken": metric("todoapp_users_registered_total", result="email_taken"),
        "created": metric("todoapp_todos_created_total", result="success"),
        "auth_ok": metric("todoapp_auth_attempts_total", result="success"),
        "auth_missing": metric("todoapp_auth_attempts_total", result="missing"),
        "auth_invalid": metric("todoapp_auth_attempts_total", result="invalid"),
    }

    ada = await register_user()
    await client.post("/v1/users/", json={"email": "ada@example.com", "name": "Ada"})
    await client.post(
        "/v1/todos/",
        json={"title": "Milk"},
        headers={"Authorization": f"Bearer {ada['api_token']}"},
    )
    await client.post("/v1/todos/", json={"title": "Milk"})
    await client.post("/v1/todos/", json={"title": "Milk"}, headers={"Authorization": "Bearer x"})

    assert metric("todoapp_users_registered_total", result="success") == before["registered"] + 1
    assert metric("todoapp_users_registered_total", result="email_taken") == before["taken"] + 1
    assert metric("todoapp_todos_created_total", result="success") == before["created"] + 1
    assert metric("todoapp_auth_attempts_total", result="success") == before["auth_ok"] + 1
    assert metric("todoapp_auth_attempts_total", result="missing") == before["auth_missing"] + 1
    assert metric("todoapp_auth_attempts_total", result="invalid") == before["auth_invalid"] + 1

    exposed = (await client.get("/metrics")).text
    for name in ("users_registered", "todos_created", "auth_attempts"):
        assert f"todoapp_{name}_total" in exposed


async def test_storage_outage_on_create_is_counted_and_500(
    client: AsyncClient,
    register_user: RegisterUser,
    metric: Metric,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ada = await register_user()

    async def broken(self: SqliteTodoRepository, todo: object) -> None:
        raise StorageUnavailableError("disk I/O error")

    monkeypatch.setattr(SqliteTodoRepository, "add", broken)
    before = metric("todoapp_todos_created_total", result="error")

    r = await client.post(
        "/v1/todos/",
        json={"title": "Milk"},
        headers={"Authorization": f"Bearer {ada['api_token']}"},
    )

    assert r.status_code == 500
    assert r.json()["code"] == "storage_error"
    assert metric("todoapp_todos_created_total", result="error") == before + 1
