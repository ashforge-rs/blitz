"""What the use cases need from the outside world; adapters implement it."""

from .clock import Clock
from .consent_ledger import ConsentLedger, DecisionTally
from .errors import (
    EventIdTakenError,
    PurposeExistsError,
    ReadOnlyUnitOfWorkError,
    StorageUnavailableError,
)
from .id_generator import IdGenerator
from .purpose_repository import PurposeRepository
from .unit_of_work import ConsentUnitOfWork, ConsentUnitOfWorkFactory

__all__ = [
    "Clock",
    "ConsentLedger",
    "ConsentUnitOfWork",
    "ConsentUnitOfWorkFactory",
    "DecisionTally",
    "EventIdTakenError",
    "IdGenerator",
    "PurposeExistsError",
    "PurposeRepository",
    "ReadOnlyUnitOfWorkError",
    "StorageUnavailableError",
]
