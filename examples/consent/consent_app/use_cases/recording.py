"""Appending a decision to the ledger exactly once, shared by GiveConsent and WithdrawConsent."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from consent_app.ports import EventIdTakenError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from consent_app.entities import ConsentEvent, ConsentStatus
    from consent_app.ports import ConsentLedger

    from .errors import ConsentError


@dataclass(frozen=True, slots=True)
class ConsentRecorded:
    event: ConsentEvent
    #: What the decision means for processing, under the deployment's profile.
    status: ConsentStatus
    #: True when an ``event_id`` retry returned the decision recorded earlier.
    replayed: bool = False


class Refusal(Exception):
    """Leave a unit of work with a refusal (nothing was written, so it rolls back empty)."""

    def __init__(self, error: ConsentError) -> None:
        self.error = error


class EventIdReusedError(Exception):
    """The client reused an ``event_id`` for a different decision."""


async def find_replay(ledger: ConsentLedger, event: ConsentEvent) -> ConsentEvent | None:
    """The earlier event if ``event`` retries it; raise if its id belongs to another decision."""
    existing = await ledger.get(event.id)
    if existing is None:
        return None
    if not existing.same_decision_as(event):
        raise EventIdReusedError
    return existing


async def retry_once_on_id_race[T](attempt: Callable[[], Awaitable[T]]) -> T:
    """A concurrent retry with the same ``event_id`` committed first: run again to replay it."""
    try:
        return await attempt()
    except EventIdTakenError:
        return await attempt()
