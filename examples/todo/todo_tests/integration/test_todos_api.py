import asyncio
import sqlite3
from contextlib import closing

import pytest
from httpx import AsyncClient

from todo_app.kernel import StorageUnavailableError
from todo_app.users.adapters.sql_user_repository import SqlUserRepository
from todo_tests.fixture_types import RegisterUser


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_returns_201_owned_by_the_caller(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    ada = await register_user()

    r = await client.post(
        "/v1/todos/", json={"title": " Buy milk "}, headers=_auth(ada["api_token"])
    )

    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Buy milk"
    assert body["owner_id"] == ada["user"]["id"]
    assert body["done"] is False


async def test_created_todo_is_in_the_database(
    client: AsyncClient, register_user: RegisterUser, db_path: str
) -> None:
    ada = await register_user()

    r = await client.post("/v1/todos/", json={"title": "Buy milk"}, headers=_auth(ada["api_token"]))

    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT id, owner_id, title FROM todos").fetchall()
    assert rows == [(r.json()["id"], ada["user"]["id"], "Buy milk")]


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer"}, {"Authorization": "Basic YWRhOnB3"}],
    ids=["no-header", "empty-bearer", "wrong-scheme"],
)
async def test_missing_credentials_are_401(client: AsyncClient, headers: dict[str, str]) -> None:
    r = await client.post("/v1/todos/", json={"title": "Buy milk"}, headers=headers)

    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_unknown_token_is_401(client: AsyncClient) -> None:
    r = await client.post("/v1/todos/", json={"title": "Buy milk"}, headers=_auth("tdo_forged"))

    assert r.status_code == 401


async def test_blank_title_is_422(client: AsyncClient, register_user: RegisterUser) -> None:
    ada = await register_user()

    r = await client.post("/v1/todos/", json={"title": "   "}, headers=_auth(ada["api_token"]))

    assert r.status_code == 422


async def test_auth_storage_outage_is_500_not_401(
    client: AsyncClient, register_user: RegisterUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    ada = await register_user()

    async def broken(self: SqlUserRepository, token_hash: str) -> None:
        raise StorageUnavailableError("database is locked")

    monkeypatch.setattr(SqlUserRepository, "find_by_token_hash", broken)

    r = await client.post("/v1/todos/", json={"title": "Buy milk"}, headers=_auth(ada["api_token"]))

    assert r.status_code == 500
    assert r.json()["code"] == "storage_error"
    assert "locked" not in r.text


async def test_retry_with_the_same_key_returns_the_original_todo(
    client: AsyncClient, register_user: RegisterUser, db_path: str
) -> None:
    ada = await register_user()
    headers = _auth(ada["api_token"]) | {"Idempotency-Key": "7d0f5e1c-0001"}

    first = await client.post("/v1/todos/", json={"title": "Buy milk"}, headers=headers)
    retry = await client.post("/v1/todos/", json={"title": "Buy milk"}, headers=headers)

    assert (first.status_code, retry.status_code) == (201, 201)
    assert retry.json() == first.json()
    assert retry.headers["idempotent-replayed"] == "true"
    assert "idempotent-replayed" not in first.headers
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT count(*) FROM todos").fetchone() == (1,)


async def test_key_reused_with_another_title_is_422(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    ada = await register_user()
    headers = _auth(ada["api_token"]) | {"Idempotency-Key": "7d0f5e1c-0001"}
    await client.post("/v1/todos/", json={"title": "Buy milk"}, headers=headers)

    r = await client.post("/v1/todos/", json={"title": "Walk dog"}, headers=headers)

    assert r.status_code == 422
    assert r.json()["code"] == "idempotency_key_reused"


async def test_another_users_key_never_replays_my_todo(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    ada = await register_user("ada@example.com")
    bob = await register_user("bob@example.com", "Bob")
    key = {"Idempotency-Key": "shared-key-0001"}

    mine = await client.post(
        "/v1/todos/", json={"title": "Milk"}, headers=_auth(ada["api_token"]) | key
    )
    theirs = await client.post(
        "/v1/todos/", json={"title": "Milk"}, headers=_auth(bob["api_token"]) | key
    )

    assert theirs.json()["id"] != mine.json()["id"]
    assert theirs.json()["owner_id"] == bob["user"]["id"]


async def test_concurrent_retries_with_one_key_create_one_todo(
    client: AsyncClient, register_user: RegisterUser, db_path: str
) -> None:
    ada = await register_user()
    headers = _auth(ada["api_token"]) | {"Idempotency-Key": "race-key-0001"}

    responses = await asyncio.gather(
        *(client.post("/v1/todos/", json={"title": "Buy milk"}, headers=headers) for _ in range(5))
    )

    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["id"] for r in responses}) == 1
    assert sum("idempotent-replayed" in r.headers for r in responses) == 4
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT count(*) FROM todos").fetchone() == (1,)
