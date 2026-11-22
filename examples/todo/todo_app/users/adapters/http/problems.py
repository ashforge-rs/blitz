from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from errors.domain import DomainError

from todo_app.users.use_cases import UserError, UserErrorCode


@dataclass(frozen=True, slots=True)
class UserProblem(DomainError[UserErrorCode]):
    """A :class:`UserError` with its HTTP status, for ResultRouter."""

    STATUS: ClassVar[Mapping[str, int]] = {
        UserErrorCode.EMAIL_TAKEN: 409,
        UserErrorCode.INVALID_TOKEN: 401,
        UserErrorCode.IDEMPOTENCY_KEY_REUSED: 422,
        # 5xx: the client sees "Internal Server Error"; the message is only logged.
        UserErrorCode.STORAGE_ERROR: 500,
    }


def to_problem(error: UserError) -> UserProblem:
    return UserProblem(error.code, error.message)
