from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime  # noqa: TC003 — dataclass field type, resolved at runtime
from enum import StrEnum
from typing import TYPE_CHECKING

from .actor import Actor  # noqa: TC001 — dataclass field type

if TYPE_CHECKING:
    from .clock import Clock
    from .ids import IdGenerator


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One audited operation, recorded by a use case inside its unit of work."""

    id: str
    operation: str
    outcome: AuditOutcome
    actor: Actor
    occurred_at: datetime
    resource_id: str | None = None
    #: Codes and identifiers only: never personal data, secrets or raw error text.
    details: dict[str, str] = field(default_factory=dict)


class AuditTrail(ABC):
    """Port: records audit entries atomically with the business change they describe."""

    @abstractmethod
    async def record(self, entry: AuditRecord) -> None: ...


class AuditEntries:
    """Builds one operation's audit records; ids and time come from the injected kernel ports."""

    def __init__(self, operation: str, *, clock: Clock, ids: IdGenerator) -> None:
        self._operation = operation
        self._clock = clock
        self._ids = ids

    def success(
        self, actor: Actor, *, resource_id: str | None = None, details: dict[str, str] | None = None
    ) -> AuditRecord:
        return self._entry(AuditOutcome.SUCCESS, actor, resource_id, details)

    def failure(self, actor: Actor, *, details: dict[str, str] | None = None) -> AuditRecord:
        return self._entry(AuditOutcome.FAILURE, actor, None, details)

    def _entry(
        self,
        outcome: AuditOutcome,
        actor: Actor,
        resource_id: str | None,
        details: dict[str, str] | None,
    ) -> AuditRecord:
        return AuditRecord(
            id=self._ids.new_id(),
            operation=self._operation,
            outcome=outcome,
            actor=actor,
            occurred_at=self._clock.now(),
            resource_id=resource_id,
            details=details or {},
        )
