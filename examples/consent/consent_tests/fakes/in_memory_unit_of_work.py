"""An in-memory consent store with real transaction semantics.

A unit of work edits a copy of the state; the copy replaces it only on a clean
exit, so a raised error discards every change, as in SQL.
"""

import copy
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from consent_app.ports import (
    ConsentLedger,
    ConsentUnitOfWork,
    ConsentUnitOfWorkFactory,
    DecisionTally,
    EventIdTakenError,
    PurposeExistsError,
    PurposeRepository,
    ReadOnlyUnitOfWorkError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from consent_app.entities import ConsentEvent, Purpose, PurposeSlug, SubjectId


def _refuse_if_read_only(read_only: bool) -> None:
    if read_only:
        msg = "write attempted in a read-only unit of work"
        raise ReadOnlyUnitOfWorkError(msg)


@dataclass
class ConsentState:
    purposes: dict[PurposeSlug, Purpose] = field(default_factory=dict)
    notices: list[tuple[PurposeSlug, str]] = field(default_factory=list)
    events: list[ConsentEvent] = field(default_factory=list)


class InMemoryConsentUnitOfWorkFactory(ConsentUnitOfWorkFactory):
    def __init__(self) -> None:
        self.state = ConsentState()
        self.commits = 0
        #: Set to make the next units of work fail on entry (an outage, or a bug).
        self.fail_with: Exception | None = None
        #: Set to simulate a concurrent retry: called (once) when ``ledger.append`` runs, it
        #: commits the winner's event into :attr:`state`; the append then loses the race.
        self.concurrent_append: Callable[[ConsentState, ConsentEvent], None] | None = None

    def __call__(self, *, read_only: bool = False) -> InMemoryConsentUnitOfWork:
        return InMemoryConsentUnitOfWork(self, read_only=read_only)


class InMemoryConsentUnitOfWork(ConsentUnitOfWork):
    def __init__(self, factory: InMemoryConsentUnitOfWorkFactory, *, read_only: bool) -> None:
        self._factory = factory
        self._read_only = read_only
        self._work = copy.deepcopy(factory.state)

    @property
    def purposes(self) -> InMemoryPurposeRepository:
        return InMemoryPurposeRepository(self._work, read_only=self._read_only)

    @property
    def ledger(self) -> InMemoryConsentLedger:
        return InMemoryConsentLedger(self._work, self._factory, read_only=self._read_only)

    async def __aenter__(self) -> Self:
        if self._factory.fail_with is not None:
            raise self._factory.fail_with
        self._work = copy.deepcopy(self._factory.state)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None and not self._read_only:
            self._factory.state = self._work
            self._factory.commits += 1


class InMemoryPurposeRepository(PurposeRepository):
    def __init__(self, state: ConsentState, *, read_only: bool) -> None:
        self._s = state
        self._read_only = read_only

    async def add(self, purpose: Purpose) -> None:
        _refuse_if_read_only(self._read_only)
        if purpose.slug in self._s.purposes:
            raise PurposeExistsError
        self._s.purposes[purpose.slug] = purpose
        self._s.notices.append((purpose.slug, purpose.notice_version.value))

    async def get(self, slug: PurposeSlug) -> Purpose | None:
        return self._s.purposes.get(slug)

    async def all(self) -> list[Purpose]:
        return [self._s.purposes[s] for s in sorted(self._s.purposes, key=lambda s: s.value)]

    async def publish_notice(self, purpose: Purpose) -> None:
        _refuse_if_read_only(self._read_only)
        self._s.purposes[purpose.slug] = purpose
        self._s.notices.append((purpose.slug, purpose.notice_version.value))


class InMemoryConsentLedger(ConsentLedger):
    def __init__(
        self, state: ConsentState, factory: InMemoryConsentUnitOfWorkFactory, *, read_only: bool
    ) -> None:
        self._s = state
        self._factory = factory
        self._read_only = read_only

    async def append(self, event: ConsentEvent) -> None:
        _refuse_if_read_only(self._read_only)
        if (race := self._factory.concurrent_append) is not None:
            self._factory.concurrent_append = None
            race(self._factory.state, event)
            raise EventIdTakenError
        if any(e.id == event.id for e in self._s.events):
            raise EventIdTakenError
        self._s.events.append(event)

    async def get(self, event_id: str) -> ConsentEvent | None:
        return next((e for e in self._s.events if e.id == event_id), None)

    async def latest(self, subject: SubjectId, purpose: PurposeSlug) -> ConsentEvent | None:
        mine = [e for e in self._s.events if e.subject == subject and e.purpose == purpose]
        return mine[-1] if mine else None

    async def latest_by_purpose(self, subject: SubjectId) -> dict[PurposeSlug, ConsentEvent]:
        return {e.purpose: e for e in self._s.events if e.subject == subject}

    async def history(self, subject: SubjectId) -> list[ConsentEvent]:
        return [e for e in self._s.events if e.subject == subject]

    async def latest_decisions(self) -> list[ConsentEvent]:
        return list({(e.subject, e.purpose): e for e in self._s.events}.values())

    async def subject_count(self) -> int:
        return len({e.subject for e in self._s.events})

    async def tallies(self) -> list[DecisionTally]:
        counts = Counter((e.decision, e.method, e.source) for e in self._s.events)
        return [DecisionTally(d, m, s, n) for (d, m, s), n in counts.items()]
