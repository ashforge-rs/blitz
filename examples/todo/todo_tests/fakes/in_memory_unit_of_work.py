"""Transaction semantics for the in-memory fakes, shared by every context.

A unit of work edits a copy of the factory's state; the copy replaces the state
only on a clean exit, so a raised error discards every change, as in SQL.  The
contract tests check that this matches the SQL adapters.
"""

import copy
from dataclasses import dataclass, field, fields, replace
from typing import TYPE_CHECKING, Self

from todo_app.kernel import (
    AuditRecord,
    AuditTrail,
    IdempotencyKeyTakenError,
    IdempotencyRecord,
    IdempotencyStore,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType


@dataclass
class InMemoryState:
    """What every context stores besides its own entities."""

    audit: list[AuditRecord] = field(default_factory=list)
    idempotency: dict[tuple[str, str], IdempotencyRecord] = field(default_factory=dict)

    def copy(self) -> Self:
        return replace(self, **{f.name: copy.copy(getattr(self, f.name)) for f in fields(self)})


class InMemoryUnitOfWorkFactory[S: InMemoryState]:
    def __init__(self, state: S) -> None:
        self.state = state
        self.commits = 0
        #: Set to make the next units of work fail on entry (simulates an outage or a bug).
        self.fail_with: Exception | None = None
        #: Set to simulate a concurrent request: called (once) when ``idempotency.add`` runs,
        #: it commits the winner's changes into :attr:`state`; the add then loses the race.
        self.concurrent_commit: Callable[[S, IdempotencyRecord], None] | None = None


class InMemoryUnitOfWork[S: InMemoryState]:
    def __init__(self, factory: InMemoryUnitOfWorkFactory[S], *, read_only: bool) -> None:
        self._factory = factory
        self._read_only = read_only
        self._work = factory.state.copy()

    @property
    def audit(self) -> InMemoryAuditTrail:
        return InMemoryAuditTrail(self._work)

    @property
    def idempotency(self) -> InMemoryIdempotencyStore[S]:
        return InMemoryIdempotencyStore(self._work, self._factory)

    async def __aenter__(self) -> Self:
        if self._factory.fail_with is not None:
            raise self._factory.fail_with
        self._work = self._factory.state.copy()
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


class InMemoryAuditTrail(AuditTrail):
    def __init__(self, state: InMemoryState) -> None:
        self._s = state

    async def record(self, entry: AuditRecord) -> None:
        self._s.audit.append(entry)


class InMemoryIdempotencyStore[S: InMemoryState](IdempotencyStore):
    def __init__(self, state: S, factory: InMemoryUnitOfWorkFactory[S]) -> None:
        self._s = state
        self._factory = factory

    async def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        return self._s.idempotency.get((scope, key))

    async def add(self, record: IdempotencyRecord) -> None:
        if (race := self._factory.concurrent_commit) is not None:
            self._factory.concurrent_commit = None
            race(self._factory.state, record)
            raise IdempotencyKeyTakenError
        if (record.scope, record.key) in self._s.idempotency:
            raise IdempotencyKeyTakenError
        self._s.idempotency[(record.scope, record.key)] = record

    async def replace(self, record: IdempotencyRecord) -> None:
        self._s.idempotency[(record.scope, record.key)] = record
