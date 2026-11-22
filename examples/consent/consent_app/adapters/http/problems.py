from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from errors.domain import DomainError

from consent_app.use_cases import ConsentError, ConsentErrorCode


@dataclass(frozen=True, slots=True)
class ConsentProblem(DomainError[ConsentErrorCode]):
    """A use case's :class:`ConsentError` with its HTTP status, for ResultRouter."""

    STATUS: ClassVar[Mapping[str, int]] = {
        ConsentErrorCode.PURPOSE_NOT_FOUND: 404,
        ConsentErrorCode.PURPOSE_EXISTS: 409,
        ConsentErrorCode.METHOD_NOT_ACCEPTED: 422,
        ConsentErrorCode.NOTICE_OUTDATED: 409,
        ConsentErrorCode.NOTICE_UNCHANGED: 409,
        ConsentErrorCode.EVENT_ID_REUSED: 409,
        # 5xx: the client sees "Internal Server Error"; the message is only logged.
        ConsentErrorCode.STORAGE_ERROR: 500,
    }


def to_problem(error: ConsentError) -> ConsentProblem:
    return ConsentProblem(error.code, error.message)
