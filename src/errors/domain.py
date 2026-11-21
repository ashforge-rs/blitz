"""
Typed domain errors carried in ``Failure(...)`` by services that return ``Result``.

A domain declares a closed set of codes and maps each to an HTTP status::

    class OrderErrorCode(StrEnum):
        NOT_FOUND = "not_found"
        STORAGE_ERROR = "storage_error"


    @dataclass(frozen=True, slots=True)
    class OrderError(DomainError[OrderErrorCode]):
        order_id: str | None = None

        STATUS: ClassVar[Mapping[str, int]] = {
            OrderErrorCode.NOT_FOUND: 404,
            OrderErrorCode.STORAGE_ERROR: 500,
        }

A route on a :class:`routing.ResultRouter` that returns ``Failure(OrderError(...))``
raises :class:`DomainFailure`, which the global handler turns into an RFC 9457
problem response with ``status``, ``detail`` and the ``code`` extension member.
No per-domain exception handler is needed.

For 5xx statuses the client sees only the reason phrase (``"Internal Server
Error"``); the real ``message`` is logged, never sent.  Override :attr:`detail`
to change what clients see.
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping
    from enum import StrEnum


@dataclass(frozen=True, slots=True)
class DomainError[C: StrEnum]:
    """Base class for a domain's typed error value."""

    code: C
    message: str

    #: Code → HTTP status.  Codes missing from the mapping are reported as 500.
    STATUS: ClassVar[Mapping[str, int]] = {}

    @property
    def status(self) -> int:
        return self.STATUS.get(self.code, 500)

    @property
    def detail(self) -> str:
        """What the client sees.  5xx errors never expose ``message``."""
        if self.status >= 500:
            return HTTPStatus(self.status).phrase
        return self.message


class DomainFailure(Exception):
    """Raised at the routing layer when a handler returns ``Failure(DomainError)``."""

    def __init__(self, error: DomainError[Any]) -> None:
        super().__init__(error.message)
        self.error = error
