"""The CLI driver: arguments in, JSON and exit codes out, through Typer's CliRunner."""

import json
from typing import Any

import pytest
import typer
from typer.testing import CliRunner, Result

from todo_app.cli.exit_codes import ExitCode
from todo_app.kernel import StorageUnavailableError
from todo_app.todos.adapters.sqlite_todo_repository import SqliteTodoRepository
from todo_tests.fakes import RecordingAuditBackend


def _invoke(runner: CliRunner, cli: typer.Typer, *args: str, token: str | None = None) -> Result:
    return runner.invoke(cli, list(args), env={"TODO_API_TOKEN": token or ""})


def _out(result: Result) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


def _err(result: Result) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.stderr)
    return payload


def _register(runner: CliRunner, cli: typer.Typer, email: str = "ada@example.com") -> str:
    result = _invoke(runner, cli, "register", "--email", email, "--name", "Ada")
    assert result.exit_code == ExitCode.OK, result.stderr
    token: str = _out(result)["api_token"]
    return token


def test_register_prints_the_user_and_token_as_json(runner: CliRunner, cli: typer.Typer) -> None:
    result = _invoke(runner, cli, "register", "--email", " Ada@Example.com ", "--name", "Ada")

    assert result.exit_code == ExitCode.OK
    body = _out(result)
    assert body["user"]["email"] == "ada@example.com"
    assert body["api_token"].startswith("tdo_")
    assert body["replayed"] is False
    assert result.stderr == ""


def test_register_is_audited_with_the_cli_as_entrypoint(
    runner: CliRunner, cli: typer.Typer, audit_log: RecordingAuditBackend
) -> None:
    _register(runner, cli)

    # Delivered when the command closed its contexts: no polling relay in a CLI.
    [event] = audit_log.operations("users.register")
    assert event.path == "cli:register"


def test_duplicate_email_is_rejected_with_exit_1(runner: CliRunner, cli: typer.Typer) -> None:
    _register(runner, cli)

    result = _invoke(runner, cli, "register", "--email", "ADA@example.com", "--name", "Eve")

    assert result.exit_code == ExitCode.REJECTED
    assert _err(result) == {"error": "email_taken", "message": "email is already registered"}
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["register", "--email", "not-an-email", "--name", "Ada"], "not a valid email address"),
        (["register", "--email", "ada@example.com", "--name", "  "], "name must be 1-100"),
        (["create-todo", "--title", "   "], "title must be 1-200"),
        (["create-todo", "--title", "x", "--idempotency-key", "short"], "--idempotency-key"),
    ],
    ids=["bad-email", "blank-name", "blank-title", "bad-key"],
)
def test_invalid_input_is_exit_2_with_the_value_objects_message(
    runner: CliRunner, cli: typer.Typer, args: list[str], message: str
) -> None:
    token = _register(runner, cli, "someone@example.com")

    result = _invoke(runner, cli, *args, token=token)

    assert result.exit_code == ExitCode.USAGE
    assert _err(result)["error"] == "invalid_input"
    assert message in _err(result)["message"]


def test_create_todo_as_the_token_owner(runner: CliRunner, cli: typer.Typer) -> None:
    token = _register(runner, cli)

    result = _invoke(runner, cli, "create-todo", "--title", " Buy milk ", token=token)

    assert result.exit_code == ExitCode.OK
    todo = _out(result)["todo"]
    assert todo["title"] == "Buy milk"
    assert todo["done"] is False


def test_retry_with_the_same_key_replays(runner: CliRunner, cli: typer.Typer) -> None:
    token = _register(runner, cli)
    args = ("create-todo", "--title", "Buy milk", "--idempotency-key", "cli-key-0001")

    first = _out(_invoke(runner, cli, *args, token=token))
    retry = _out(_invoke(runner, cli, *args, token=token))

    assert retry["replayed"] is True
    assert retry["todo"] == first["todo"]


@pytest.mark.parametrize(
    ("token", "error"), [("", "missing_token"), ("tdo_forged", "invalid_token")]
)
def test_missing_or_unknown_token_is_exit_77(
    runner: CliRunner, cli: typer.Typer, token: str, error: str
) -> None:
    result = _invoke(runner, cli, "create-todo", "--title", "x", token=token)

    assert result.exit_code == ExitCode.NOPERM
    assert _err(result)["error"] == error


def test_storage_outage_is_exit_75_so_callers_can_retry(
    runner: CliRunner, cli: typer.Typer, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _register(runner, cli)

    async def unavailable(self: SqliteTodoRepository, todo: object) -> None:
        raise StorageUnavailableError("database is locked")

    monkeypatch.setattr(SqliteTodoRepository, "add", unavailable)

    result = _invoke(runner, cli, "create-todo", "--title", "x", token=token)

    assert result.exit_code == ExitCode.TEMPFAIL
    assert _err(result) == {"error": "storage_error", "message": "storage unavailable"}


def test_missing_option_is_a_usage_error(runner: CliRunner, cli: typer.Typer) -> None:
    result = _invoke(runner, cli, "create-todo")

    assert result.exit_code == ExitCode.USAGE
    assert "--title" in result.stderr


def test_the_token_is_not_a_command_line_option(runner: CliRunner, cli: typer.Typer) -> None:
    result = _invoke(runner, cli, "create-todo", "--help")

    assert "--token" not in result.stdout
    assert "TODO_API_TOKEN" in result.stdout
