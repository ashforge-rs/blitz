"""A Typer app wired to the test database and the recording audit backend."""

import pytest
import typer
from typer.testing import CliRunner

from todo_app.cli.main import create_cli
from todo_app.settings import TodoSettings
from todo_tests.fakes import RecordingAuditBackend


@pytest.fixture
def cli(db_path: str, audit_log: RecordingAuditBackend) -> typer.Typer:
    settings = TodoSettings(_env_file=None, DB_PATH=db_path)  # type: ignore[call-arg]  # pydantic-settings init kwarg
    return create_cli(settings=settings, audit_backend=audit_log, configure_logs=False)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
