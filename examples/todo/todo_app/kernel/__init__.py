"""Shared kernel: values and ports every context's inner layers may use.

Pure standard library, like the inner layers themselves (see the dependency-rule
test in ``todo_tests/architecture``).
"""

from .actor import Actor
from .audit import AuditEntries, AuditOutcome, AuditRecord, AuditTrail
from .clock import Clock, SystemClock
from .errors import StorageUnavailableError
from .idempotency import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    IDEMPOTENCY_KEY_MIN_LENGTH,
    IDEMPOTENCY_KEY_PATTERN,
    IDEMPOTENCY_TTL,
    IdempotencyConflictError,
    IdempotencyKeyTakenError,
    IdempotencyRecord,
    IdempotencyStore,
    fingerprint,
    is_valid_idempotency_key,
    retry_once_on_key_race,
)
from .ids import IdGenerator, Uuid7Ids

__all__ = [
    "IDEMPOTENCY_KEY_MAX_LENGTH",
    "IDEMPOTENCY_KEY_MIN_LENGTH",
    "IDEMPOTENCY_KEY_PATTERN",
    "IDEMPOTENCY_TTL",
    "Actor",
    "AuditEntries",
    "AuditOutcome",
    "AuditRecord",
    "AuditTrail",
    "Clock",
    "IdGenerator",
    "IdempotencyConflictError",
    "IdempotencyKeyTakenError",
    "IdempotencyRecord",
    "IdempotencyStore",
    "StorageUnavailableError",
    "SystemClock",
    "Uuid7Ids",
    "fingerprint",
    "is_valid_idempotency_key",
    "retry_once_on_key_race",
]
