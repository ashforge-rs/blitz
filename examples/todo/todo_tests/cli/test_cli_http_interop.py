"""The proof: two drivers, one core.  CLI and HTTP share the database and the rules.

The CLI runs in a worker thread (it starts its own event loop, as in a real
process) while the HTTP app serves on the test's loop; both open the same file.
"""

import asyncio
import json
from typing import Any

import typer
from httpx import AsyncClient
from typer.testing import CliRunner, Result

from todo_app.cli.exit_codes import ExitCode
from todo_tests.fixture_types import RegisterUser


async def _cli(runner: CliRunner, cli: typer.Typer, *args: str, token: str = "") -> Result:
    return await asyncio.to_thread(runner.invoke, cli, list(args), env={"TODO_API_TOKEN": token})


def _json(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(text)
    return payload


async def test_a_token_issued_by_the_cli_works_over_http(
    runner: CliRunner, cli: typer.Typer, client: AsyncClient
) -> None:
    registered = await _cli(runner, cli, "register", "--email", "ada@example.com", "--name", "Ada")
    body = _json(registered.stdout)

    r = await client.post(
        "/v1/todos/",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {body['api_token']}"},
    )

    assert r.status_code == 201
    assert r.json()["owner_id"] == body["user"]["id"]


async def test_a_token_issued_over_http_works_in_the_cli(
    runner: CliRunner, cli: typer.Typer, register_user: RegisterUser
) -> None:
    ada = await register_user()

    result = await _cli(runner, cli, "create-todo", "--title", "Buy milk", token=ada["api_token"])

    assert result.exit_code == ExitCode.OK
    assert _json(result.stdout)["todo"]["owner_id"] == ada["user"]["id"]


async def test_one_idempotency_key_spans_both_drivers(
    runner: CliRunner, cli: typer.Typer, client: AsyncClient, register_user: RegisterUser
) -> None:
    ada = await register_user()
    key = "shared-key-0001"

    from_cli = await _cli(
        runner,
        cli,
        "create-todo",
        "--title",
        "Buy milk",
        "--idempotency-key",
        key,
        token=ada["api_token"],
    )
    over_http = await client.post(
        "/v1/todos/",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {ada['api_token']}", "Idempotency-Key": key},
    )

    assert over_http.headers["idempotent-replayed"] == "true"
    assert over_http.json()["id"] == _json(from_cli.stdout)["todo"]["id"]


async def test_both_drivers_reject_the_same_input_with_the_same_rule(
    runner: CliRunner, cli: typer.Typer, client: AsyncClient
) -> None:
    from_cli = await _cli(runner, cli, "register", "--email", "nope", "--name", "Ada")
    over_http = await client.post("/v1/users/", json={"email": "nope", "name": "Ada"})

    assert from_cli.exit_code == ExitCode.USAGE
    assert over_http.status_code == 422
    message = _json(from_cli.stderr)["message"]
    assert message == "not a valid email address"
    assert message in over_http.text


async def test_both_drivers_see_one_set_of_users(
    runner: CliRunner, cli: typer.Typer, register_user: RegisterUser
) -> None:
    await register_user(email="ada@example.com")

    result = await _cli(runner, cli, "register", "--email", "ADA@example.com", "--name", "Eve")

    assert result.exit_code == ExitCode.REJECTED
    assert _json(result.stderr)["error"] == "email_taken"
