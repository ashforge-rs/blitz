"""
Typed domain errors for the *items* bounded context.

Pattern-match on :class:`ItemErrorCode` in callers to decide the appropriate
retry strategy.  Never inspect the ``message`` string for control flow — it is a
human-readable description only.

HTTP mapping lives in :attr:`ItemError.STATUS`; the framework turns a
``Failure(ItemError(...))`` returned from a route into a problem response
(see :mod:`errors.domain`).
"""

from collections.abc import Mapping  # noqa: TC003 — evaluated at runtime by dataclass ClassVar
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from errors.domain import DomainError


class ItemErrorCode(StrEnum):
    """Closed set of machine-readable error codes for the items domain."""

    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    STORAGE_ERROR = "storage_error"


@dataclass(frozen=True, slots=True)
class ItemError(DomainError[ItemErrorCode]):
    """Immutable, typed domain error for the *items* bounded context.

    ``item_id`` is optional and only used for correlation with audit logs.
    """

    item_id: str | None = None

    STATUS: ClassVar[Mapping[str, int]] = {
        ItemErrorCode.NOT_FOUND: 404,
        ItemErrorCode.CONFLICT: 409,
        # 5xx: the client sees "Internal Server Error"; the message is only logged.
        ItemErrorCode.STORAGE_ERROR: 500,
    }
