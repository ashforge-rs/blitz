"""CLI adapter: arguments → value objects → use case → JSON on stdout / stderr + exit code.

The mirror image of ``adapters/http/``: same use cases, same validation (the
value objects), same errors, another delivery mechanism.
"""

import json
import uuid
from typing import TYPE_CHECKING, Any

import typer
from returns.pipeline import is_successful

from todo_app.kernel import Actor, is_valid_idempotency_key
from todo_app.todos.entities import Title
from todo_app.todos.use_cases import TodoErrorCode
from todo_app.users.entities import DisplayName, EmailAddress
from todo_app.users.use_cases import UserErrorCode

from .exit_codes import ExitCode

if TYPE_CHECKING:
    from collections.abc import Mapping

    from todo_app.todos.entities import Todo
    from todo_app.todos.use_cases import TodoError
    from todo_app.users.entities import User
    from todo_app.users.use_cases import UserError

    from .composition import Services

#: Environment variable holding the caller's API token.  A flag would leak the
#: secret into shell history and the process list.
TOKEN_ENV = "TODO_API_TOKEN"  # noqa: S105 — the variable's name, not a secret

_EXIT_FOR = {
    UserErrorCode.EMAIL_TAKEN: ExitCode.REJECTED,
    UserErrorCode.IDEMPOTENCY_KEY_REUSED: ExitCode.REJECTED,
    UserErrorCode.INVALID_TOKEN: ExitCode.NOPERM,
    UserErrorCode.STORAGE_ERROR: ExitCode.TEMPFAIL,
    TodoErrorCode.IDEMPOTENCY_KEY_REUSED: ExitCode.REJECTED,
    TodoErrorCode.STORAGE_ERROR: ExitCode.TEMPFAIL,
}


class Console:
    """Results as one JSON object on stdout; errors as one JSON object on stderr."""

    def result(self, payload: Mapping[str, Any]) -> ExitCode:
        typer.echo(json.dumps(payload, sort_keys=True))
        return ExitCode.OK

    def error(self, code: str, message: str, exit_code: ExitCode) -> ExitCode:
        typer.echo(json.dumps({"error": code, "message": message}), err=True)
        return exit_code

    def failure(self, error: UserError | TodoError) -> ExitCode:
        return self.error(error.code.value, error.message, _EXIT_FOR[error.code])


def _actor(command: str, user_id: str | None = None) -> Actor:
    return Actor(user_id=user_id, correlation_id=uuid.uuid4().hex, entrypoint=f"cli:{command}")


def _idempotency_key(key: str | None) -> str | None:
    if key is not None and not is_valid_idempotency_key(key):
        msg = "--idempotency-key must be 8-255 printable characters"
        raise ValueError(msg)
    return key


async def register(
    services: Services,
    console: Console,
    *,
    email: str,
    name: str,
    idempotency_key: str | None,
) -> ExitCode:
    try:
        valid_email, valid_name = EmailAddress(email), DisplayName(name)
        key = _idempotency_key(idempotency_key)
    except ValueError as exc:
        return console.error("invalid_input", str(exc), ExitCode.USAGE)

    result = await services.users.register.execute(
        valid_email, valid_name, _actor("register"), idempotency_key=key
    )
    if not is_successful(result):
        return console.failure(result.failure())
    registration = result.unwrap()
    return console.result(
        {
            "user": _user(registration.user),
            "api_token": registration.api_token,
            "replayed": registration.replayed,
        }
    )


async def create_todo(
    services: Services,
    console: Console,
    *,
    title: str,
    idempotency_key: str | None,
    token: str | None,
) -> ExitCode:
    token = (token or "").strip()
    if not token:
        return console.error("missing_token", f"set {TOKEN_ENV} to your API token", ExitCode.NOPERM)
    try:
        valid_title = Title(title)
        key = _idempotency_key(idempotency_key)
    except ValueError as exc:
        return console.error("invalid_input", str(exc), ExitCode.USAGE)

    authenticated = await services.users.authenticate.execute(token, _actor("create-todo"))
    if not is_successful(authenticated):
        return console.failure(authenticated.failure())
    owner = authenticated.unwrap()

    result = await services.todos.create.execute(
        owner.id, valid_title, _actor("create-todo", owner.id), idempotency_key=key
    )
    if not is_successful(result):
        return console.failure(result.failure())
    created = result.unwrap()
    return console.result({"todo": _todo(created.todo), "replayed": created.replayed})


def _user(user: User) -> dict[str, str]:
    return {
        "id": user.id,
        "email": user.email.value,
        "name": user.name.value,
        "created_at": user.created_at.isoformat(),
    }


def _todo(todo: Todo) -> dict[str, Any]:
    return {
        "id": todo.id,
        "owner_id": todo.owner_id,
        "title": todo.title.value,
        "done": todo.done,
        "created_at": todo.created_at.isoformat(),
    }
