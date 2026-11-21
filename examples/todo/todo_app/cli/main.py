"""Typer entry point: parses the command line, runs one command, exits with its code."""

import asyncio
import os
import sys
from typing import TYPE_CHECKING, Annotated

import typer
from loguru import logger

from todo_app.settings import TodoSettings

from . import commands
from .composition import open_services

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from audit.backend import AuditBackend
    from loguru import Record

    from .composition import Services
    from .exit_codes import ExitCode

#: blitz's LoguruAuditBackend writes audit events through loguru under this name.
_AUDIT_LOGGER = "audit.backends.loguru"

IdempotencyKey = Annotated[
    str | None,
    typer.Option(
        "--idempotency-key",
        help="Random value (a UUID). Retrying with the same key repeats nothing.",
        show_default=False,
    ),
]


def configure_logging(*, verbose: bool) -> None:
    """Diagnostics to stderr (stdout carries only the JSON result).

    Audit events are not diagnostics: they pass whatever the verbosity, or a
    quiet run would silently drop the audit trail of every successful command.
    """
    threshold = logger.level("INFO" if verbose else "WARNING").no

    def keep(record: Record) -> bool:
        return record["name"] == _AUDIT_LOGGER or record["level"].no >= threshold

    logger.remove()
    logger.add(sys.stderr, level=0, filter=keep)


def create_cli(
    *,
    settings: TodoSettings | None = None,
    audit_backend: AuditBackend | None = None,
    configure_logs: bool = True,
) -> typer.Typer:
    """The CLI application.  Tests inject settings and an audit backend; ``configure_logs``
    is off there so a test run doesn't replace the process's log handlers."""
    cli = typer.Typer(
        help="Todo app command line: the same use cases as the HTTP API.",
        epilog=f"create-todo authenticates with the API token in ${commands.TOKEN_ENV}.",
        no_args_is_help=True,
        add_completion=False,
        # Rich tracebacks print local variables, which would include API tokens.
        pretty_exceptions_enable=False,
    )

    def run(command: Callable[[Services, commands.Console], Awaitable[ExitCode]]) -> None:
        async def _with_services() -> ExitCode:
            async with open_services(
                settings or TodoSettings(), audit_backend=audit_backend
            ) as services:
                return await command(services, commands.Console())

        raise typer.Exit(asyncio.run(_with_services()))

    @cli.callback()
    def _root(
        verbose: Annotated[
            bool, typer.Option("--verbose", "-v", help="Log diagnostics to stderr.")
        ] = False,
    ) -> None:
        if configure_logs:
            configure_logging(verbose=verbose)

    @cli.command()
    def register(
        email: Annotated[str, typer.Option(help="The user's email address.")],
        name: Annotated[str, typer.Option(help="The user's display name.")],
        idempotency_key: IdempotencyKey = None,
    ) -> None:
        """Register a user and print their API token (shown once)."""
        run(
            lambda services, console: commands.register(
                services, console, email=email, name=name, idempotency_key=idempotency_key
            )
        )

    @cli.command("create-todo")
    def create_todo(
        title: Annotated[str, typer.Option(help="What to do.")],
        idempotency_key: IdempotencyKey = None,
    ) -> None:
        """Create a todo owned by the user whose API token is in $TODO_API_TOKEN."""
        # Read from the environment, never a flag: argv leaks into shell history and `ps`.
        token = os.environ.get(commands.TOKEN_ENV)
        run(
            lambda services, console: commands.create_todo(
                services, console, title=title, idempotency_key=idempotency_key, token=token
            )
        )

    return cli


def main(prog_name: str | None = None) -> None:
    """Entry point of the ``todo`` console script and of ``python -m todo_app.cli``."""
    create_cli()(prog_name=prog_name)
