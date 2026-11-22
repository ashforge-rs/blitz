from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from consent_app.entities import ConsentDecision, ConsentMethod  # noqa: TC001 — dataclass fields

if TYPE_CHECKING:
    from consent_app.entities import ConsentEvent, PurposeSlug, SubjectId


@dataclass(frozen=True, slots=True)
class DecisionTally:
    """How many ledger events share a decision, method and channel (for reporting)."""

    decision: ConsentDecision
    method: ConsentMethod | None
    source: str
    count: int


class ConsentLedger(ABC):
    """Port: the append-only record of every consent decision.

    Events are never updated or deleted: the ledger is the proof that consent was
    given (and when it was withdrawn).  Order is recording order.
    """

    @abstractmethod
    async def append(self, event: ConsentEvent) -> None:
        """Record an event; raise ``EventIdTakenError`` if its id already exists."""

    @abstractmethod
    async def get(self, event_id: str) -> ConsentEvent | None: ...

    @abstractmethod
    async def latest(self, subject: SubjectId, purpose: PurposeSlug) -> ConsentEvent | None:
        """The subject's most recent decision about ``purpose``."""

    @abstractmethod
    async def latest_by_purpose(self, subject: SubjectId) -> dict[PurposeSlug, ConsentEvent]:
        """The subject's most recent decision about each purpose they decided on."""

    @abstractmethod
    async def history(self, subject: SubjectId) -> list[ConsentEvent]:
        """Every decision the subject made, oldest first."""

    # Reporting: aggregate reads over the whole ledger.

    @abstractmethod
    async def latest_decisions(self) -> list[ConsentEvent]:
        """Every subject's most recent decision about each purpose they decided on."""

    @abstractmethod
    async def subject_count(self) -> int:
        """How many distinct subjects the ledger knows."""

    @abstractmethod
    async def tallies(self) -> list[DecisionTally]:
        """Event counts by decision, method and source."""
