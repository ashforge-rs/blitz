from dataclasses import dataclass
from enum import StrEnum


class ConsentErrorCode(StrEnum):
    PURPOSE_NOT_FOUND = "purpose_not_found"
    PURPOSE_EXISTS = "purpose_exists"
    METHOD_NOT_ACCEPTED = "method_not_accepted"
    NOTICE_OUTDATED = "notice_outdated"
    NOTICE_UNCHANGED = "notice_unchanged"
    EVENT_ID_REUSED = "event_id_reused"
    STORAGE_ERROR = "storage_error"


_MESSAGES = {
    ConsentErrorCode.PURPOSE_NOT_FOUND: "no such purpose",
    ConsentErrorCode.PURPOSE_EXISTS: "a purpose with this slug already exists",
    ConsentErrorCode.METHOD_NOT_ACCEPTED: "this method does not count as consent under the profile",
    ConsentErrorCode.NOTICE_OUTDATED: "the subject saw an outdated notice: show the current one",
    ConsentErrorCode.NOTICE_UNCHANGED: "this notice version is already current",
    ConsentErrorCode.EVENT_ID_REUSED: "event_id already used for a different decision",
    ConsentErrorCode.STORAGE_ERROR: "storage unavailable",
}


@dataclass(frozen=True, slots=True)
class ConsentError:
    """Why a use case refused.  The HTTP mapping lives in ``adapters/http/problems.py``.

    ``message`` is safe to show: it never contains raw driver errors.
    """

    code: ConsentErrorCode
    message: str


def consent_error(code: ConsentErrorCode, detail: str | None = None) -> ConsentError:
    message = _MESSAGES[code]
    return ConsentError(code, f"{message} ({detail})" if detail else message)
