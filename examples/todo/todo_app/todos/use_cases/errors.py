from dataclasses import dataclass
from enum import StrEnum


class TodoErrorCode(StrEnum):
    IDEMPOTENCY_KEY_REUSED = "idempotency_key_reused"
    STORAGE_ERROR = "storage_error"


@dataclass(frozen=True, slots=True)
class TodoError:
    """Why a todos use case failed.  The HTTP mapping lives in ``adapters/http/problems.py``.

    ``message`` is safe to show and to audit: it never contains raw driver errors.
    """

    code: TodoErrorCode
    message: str


MESSAGES = {
    TodoErrorCode.IDEMPOTENCY_KEY_REUSED: "Idempotency-Key already used for another request",
    TodoErrorCode.STORAGE_ERROR: "storage unavailable",
}


def todo_error(code: TodoErrorCode) -> TodoError:
    return TodoError(code, MESSAGES[code])
