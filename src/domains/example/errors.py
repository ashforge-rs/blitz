"""
Typed domain errors for the *items* bounded context.

Pattern-match on :class:`ItemErrorCode` in callers to decide the appropriate
HTTP status code or retry strategy.  Never inspect the ``message`` string for
control flow — it is a human-readable description only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ItemErrorCode(StrEnum):
    """Closed set of machine-readable error codes for the items domain.

    Adding a new value forces every ``match error.code:`` block to either
    handle it explicitly or use a wildcard ``case _:`` — making exhaustiveness
    visible at review time.
    """

    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    STORAGE_ERROR = "storage_error"


@dataclass(frozen=True, slots=True)
class ItemError:
    """Immutable, typed domain error for the *items* bounded context.

    Fields
    ------
    code:
        Machine-readable :class:`ItemErrorCode` — use this for branching.
    message:
        Human-readable description.  Safe to surface in non-production HTTP
        responses; never include secrets or internal stack traces here.
    item_id:
        Optional item identifier for correlation with audit logs.
    """

    code: ItemErrorCode
    message: str
    item_id: str | None = None


class ItemDomainError(Exception):
    """Raised by endpoint handlers when the service returns a :class:`Failure`.

    The domain exception handler (``register_exception_handlers``) intercepts
    this at the ASGI boundary and converts it to the appropriate HTTP response,
    keeping all HTTP-mapping logic in one place.
    """

    def __init__(self, error: ItemError) -> None:
        super().__init__(error.message)
        self.error = error
