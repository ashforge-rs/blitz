from typing import Any

import pytest
from httpx import AsyncClient

from todo_tests.fixture_types import RegisterUser


async def test_register_returns_201_with_user_and_token(client: AsyncClient) -> None:
    r = await client.post("/v1/users/", json={"email": "Ada@Example.com", "name": " Ada "})

    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["name"] == "Ada"
    assert body["api_token"].startswith("tdo_")


async def test_duplicate_email_is_a_409_problem(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    await register_user(email="ada@example.com")

    r = await client.post("/v1/users/", json={"email": "ADA@example.com", "name": "Imposter"})

    assert r.status_code == 409
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "email_taken"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "name": "Ada"},
        {"email": "ada@example.com", "name": "   "},
        {"email": "ada@example.com"},
        {"email": "ada@example.com", "name": "Ada", "is_admin": True},
    ],
    ids=["bad-email", "blank-name", "missing-name", "unknown-field"],
)
async def test_invalid_registration_is_422(client: AsyncClient, payload: dict[str, Any]) -> None:
    r = await client.post("/v1/users/", json=payload)

    assert r.status_code == 422


async def test_422_does_not_echo_the_rejected_email(client: AsyncClient) -> None:
    r = await client.post("/v1/users/", json={"email": "private-person", "name": "Ada"})

    assert r.status_code == 422
    assert "not a valid email address" in r.text


async def test_openapi_documents_the_length_limits(client: AsyncClient) -> None:
    schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]

    assert schemas["RegisterUserBody"]["properties"]["email"]["maxLength"] == 254


async def test_retried_registration_returns_the_user_with_a_working_new_token(
    client: AsyncClient,
) -> None:
    body = {"email": "ada@example.com", "name": "Ada"}
    key = {"Idempotency-Key": "3b8e2a90-0001"}

    first = await client.post("/v1/users/", json=body, headers=key)
    retry = await client.post("/v1/users/", json=body, headers=key)

    assert (first.status_code, retry.status_code) == (201, 201)
    assert retry.headers["idempotent-replayed"] == "true"
    assert retry.json()["user"] == first.json()["user"]
    old, new = first.json()["api_token"], retry.json()["api_token"]
    assert old != new

    async def create_with(token: str) -> int:
        r = await client.post(
            "/v1/todos/", json={"title": "x"}, headers={"Authorization": f"Bearer {token}"}
        )
        return r.status_code

    assert await create_with(new) == 201
    assert await create_with(old) == 401  # the undelivered token was revoked


async def test_key_reused_for_another_registration_is_422(client: AsyncClient) -> None:
    key = {"Idempotency-Key": "3b8e2a90-0001"}
    await client.post("/v1/users/", json={"email": "ada@example.com", "name": "Ada"}, headers=key)

    r = await client.post(
        "/v1/users/", json={"email": "bob@example.com", "name": "Bob"}, headers=key
    )

    assert r.status_code == 422
    assert r.json()["code"] == "idempotency_key_reused"


@pytest.mark.parametrize("key", ["short", "has space-1234", "x" * 256])
async def test_malformed_idempotency_key_is_422(client: AsyncClient, key: str) -> None:
    r = await client.post(
        "/v1/users/",
        json={"email": "ada@example.com", "name": "Ada"},
        headers={"Idempotency-Key": key},
    )

    assert r.status_code == 422
