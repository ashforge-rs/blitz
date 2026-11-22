from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — dataclass field type, resolved at runtime
from enum import StrEnum

from .purpose_slug import PurposeSlug  # noqa: TC001 — dataclass field type


class ConsentState(StrEnum):
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    NOT_GIVEN = "not_given"
    EXPIRED = "expired"
    #: Granted under a notice that has since changed: ask again.
    RENEWAL_REQUIRED = "renewal_required"


@dataclass(frozen=True, slots=True)
class ConsentStatus:
    """Whether processing for a purpose may go ahead for a subject, and why."""

    purpose: PurposeSlug
    state: ConsentState
    #: The answer client systems act on.
    may_process: bool
    #: When the deciding event was recorded (``None`` if there is none).
    since: datetime | None = None
    #: The event the state is derived from.
    event_id: str | None = None
