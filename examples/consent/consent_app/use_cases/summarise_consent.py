from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from consent_app.ports import StorageUnavailableError

from .errors import ConsentError, ConsentErrorCode, consent_error

if TYPE_CHECKING:
    from consent_app.entities import ConsentState, ConsentStatus, Purpose, PurposeSlug
    from consent_app.ports import Clock, ConsentUnitOfWorkFactory, DecisionTally
    from consent_app.profiles import RegulationProfile


@dataclass(slots=True)
class PurposeSummary:
    purpose: Purpose
    states: Counter[ConsentState] = field(default_factory=Counter)
    #: Subjects whose data may be processed for this purpose right now.
    may_process: int = 0


@dataclass(frozen=True, slots=True)
class ConsentSummary:
    subjects: int
    purposes: dict[PurposeSlug, PurposeSummary]
    tallies: list[DecisionTally]


class SummariseConsent:
    """Where every known subject stands on every purpose, judged by the profile.

    The same rules as GetConsentStatus, applied in bulk, so a dashboard shows exactly
    what the API would answer.  It reads the whole ledger: fine for reporting at
    this scale; a large deployment would maintain a read model instead.
    """

    def __init__(
        self, uow: ConsentUnitOfWorkFactory, profile: RegulationProfile, *, clock: Clock
    ) -> None:
        self._uow = uow
        self._profile = profile
        self._clock = clock

    async def execute(self) -> Result[ConsentSummary, ConsentError]:
        try:
            async with self._uow(read_only=True) as uow:
                purposes = await uow.purposes.all()
                latest = await uow.ledger.latest_decisions()
                subjects = await uow.ledger.subject_count()
                tallies = await uow.ledger.tallies()
        except StorageUnavailableError:
            return Failure(consent_error(ConsentErrorCode.STORAGE_ERROR))

        now = self._clock.now()
        summaries = {p.slug: PurposeSummary(p) for p in purposes}
        decided: Counter[PurposeSlug] = Counter()
        for event in latest:
            if (summary := summaries.get(event.purpose)) is None:
                continue
            _count(summary, self._profile.status(summary.purpose, event, now), 1)
            decided[event.purpose] += 1
        for slug, summary in summaries.items():
            if never_asked := subjects - decided[slug]:
                _count(summary, self._profile.status(summary.purpose, None, now), never_asked)
        return Success(ConsentSummary(subjects, summaries, tallies))


def _count(summary: PurposeSummary, status: ConsentStatus, subjects: int) -> None:
    summary.states[status.state] += subjects
    if status.may_process:
        summary.may_process += subjects
