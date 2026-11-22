"""`todo seed`: demo data through the use cases, safe to re-run, never in production."""

import json
import sqlite3
from contextlib import closing

import typer
from pydantic import SecretStr
from typer.testing import CliRunner

from todo_app.cli.exit_codes import ExitCode
from todo_app.cli.main import create_cli
from todo_app.cli.seed import DEMO_USERS
from todo_app.settings import TodoSettings


def _cli(database_url: str, environment: str = "development") -> typer.Typer:
    settings = TodoSettings(_env_file=None, DATABASE_URL=SecretStr(database_url))  # type: ignore[call-arg]  # pydantic-settings init kwarg
    return create_cli(settings=settings, configure_logs=False, environment=environment)


def _count(db_path: str, table: str) -> int:
    with closing(sqlite3.connect(db_path)) as conn:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608 — test constant


def test_seed_loads_every_demo_user_and_todo(
    runner: CliRunner, database_url: str, db_path: str
) -> None:
    result = runner.invoke(_cli(database_url), ["seed"])

    assert result.exit_code == ExitCode.OK, result.output
    report = json.loads(result.stdout)
    assert report["replayed"] is False
    assert [(u["email"], u["todos"]) for u in report["users"]] == [
        (email, len(titles)) for email, _, titles in DEMO_USERS
    ]
    assert _count(db_path, "users") == len(DEMO_USERS)
    assert _count(db_path, "todos") == sum(len(titles) for _, _, titles in DEMO_USERS)


def test_the_printed_tokens_work(runner: CliRunner, database_url: str) -> None:
    cli = _cli(database_url)
    [ada, *_] = json.loads(runner.invoke(cli, ["seed"]).stdout)["users"]

    created = runner.invoke(
        cli, ["create-todo", "--title", "One more"], env={"TODO_API_TOKEN": ada["api_token"]}
    )

    assert created.exit_code == ExitCode.OK, created.output


def test_a_rerun_records_nothing_twice(runner: CliRunner, database_url: str, db_path: str) -> None:
    cli = _cli(database_url)
    runner.invoke(cli, ["seed"])
    counts = (_count(db_path, "users"), _count(db_path, "todos"))

    again = json.loads(runner.invoke(cli, ["seed"]).stdout)

    assert again["replayed"] is True
    assert (_count(db_path, "users"), _count(db_path, "todos")) == counts


def test_seeding_is_refused_in_production(
    runner: CliRunner, database_url: str, db_path: str
) -> None:
    result = runner.invoke(_cli(database_url, environment="production"), ["seed"])

    assert result.exit_code == ExitCode.CONFIG
    assert json.loads(result.stderr)["error"] == "seed_refused"
    assert _count(db_path, "users") == 0


def test_users_registered_outside_the_replay_window_are_skipped(
    runner: CliRunner, database_url: str, db_path: str
) -> None:
    cli = _cli(database_url)
    # Ada registered on her own (no seed key): like a seed run older than 24 h.
    runner.invoke(cli, ["register", "--email", "ada@example.com", "--name", "Ada Lovelace"])

    report = json.loads(runner.invoke(cli, ["seed"]).stdout)

    assert report["already_present"] == ["ada@example.com"]
    assert [u["email"] for u in report["users"]] == ["grace@example.com", "alan@example.com"]
    assert _count(db_path, "users") == len(DEMO_USERS)


def test_an_unavailable_database_is_a_clean_error(runner: CliRunner) -> None:
    result = runner.invoke(_cli("sqlite+aiosqlite:////nonexistent-dir/todo.db"), ["seed"])

    assert result.exit_code == ExitCode.TEMPFAIL
    assert json.loads(result.stderr)["error"] == "storage_unavailable"
