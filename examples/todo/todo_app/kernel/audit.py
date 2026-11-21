from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime  # noqa: TC003 — dataclass field type, resolved at runtime
from enum import StrEnum

from .actor import Actor  # noqa: TC001 — dataclass field type


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
