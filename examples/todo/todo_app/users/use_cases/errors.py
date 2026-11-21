from dataclasses import dataclass
from enum import StrEnum


class UserErrorCode(StrEnum):
    EMAIL_TAKEN = "email_taken"
    INVALID_TOKEN = "invalid_token"  # noqa: S105 — an error code, not a secret
    IDEMPOTENCY_KEY_REUSED = "idempotency_key_reused"
    STORAGE_ERROR = "storage_error"


@dataclass(frozen=True, slots=True)
class UserError:
    """Why a users use case failed.  The HTTP mapping lives in ``adapters/http/problems.py``.

    ``message`` is safe to show and to audit: it never contains raw driver errors.
    """

    code: UserErrorCode
    message: str


MESSAGES = {
    UserErrorCode.EMAIL_TAKEN: "email is already registered",
    UserErrorCode.INVALID_TOKEN: "invalid API token",
    UserErrorCode.IDEMPOTENCY_KEY_REUSED: "Idempotency-Key already used for another request",
    UserErrorCode.STORAGE_ERROR: "storage unavailable",
}


def user_error(code: UserErrorCode) -> UserError:
    return UserError(code, MESSAGES[code])
