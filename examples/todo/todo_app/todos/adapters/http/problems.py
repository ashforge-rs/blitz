from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from errors.domain import DomainError

from todo_app.todos.use_cases import TodoError, TodoErrorCode


@dataclass(frozen=True, slots=True)
class TodoProblem(DomainError[TodoErrorCode]):
    """A :class:`TodoError` with its HTTP status, for ResultRouter."""

    STATUS: ClassVar[Mapping[str, int]] = {
        TodoErrorCode.IDEMPOTENCY_KEY_REUSED: 422,
        # 5xx: the client sees "Internal Server Error"; the message is only logged.
        TodoErrorCode.STORAGE_ERROR: 500,
    }


def to_problem(error: TodoError) -> TodoProblem:
    return TodoProblem(error.code, error.message)
