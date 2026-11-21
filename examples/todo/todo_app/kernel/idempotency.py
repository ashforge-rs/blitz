import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

#: How long a completed request can be replayed.  After that the key is free again.
IDEMPOTENCY_TTL = timedelta(hours=24)

#: A key is 8-255 printable, non-space ASCII characters (a UUID fits).  Every driver
#: (HTTP header, CLI flag) enforces this same rule.
IDEMPOTENCY_KEY_MIN_LENGTH = 8
IDEMPOTENCY_KEY_MAX_LENGTH = 255
IDEMPOTENCY_KEY_PATTERN = r"^[\x21-\x7e]+$"


def is_valid_idempotency_key(key: str) -> bool:
    return (
        IDEMPOTENCY_KEY_MIN_LENGTH <= len(key) <= IDEMPOTENCY_KEY_MAX_LENGTH
        and re.fullmatch(IDEMPOTENCY_KEY_PATTERN, key) is not None
    )


class IdempotencyConflictError(Exception):
    """The key was already used for a request with different content."""


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """What a completed request created, keyed by the client's Idempotency-Key."""

    #: Namespace of the key, e.g. ``"todos.create:<user id>"``: keys never collide across
    #: operations or users.
    scope: str
    key: str
    #: Hash of the request's meaningful content; a reused key with other content is refused.
    request_fingerprint: str
    resource_id: str
    created_at: datetime
    #: Operation-specific reference, e.g. the hash of the token a registration issued.
    secret_ref: str | None = None

    def is_live(self, now: datetime) -> bool:
        return now - self.created_at < IDEMPOTENCY_TTL


class IdempotencyStore(ABC):
    """Port: completed requests by ``(scope, key)``, inside the current unit of work."""

    @abstractmethod
    async def get(self, scope: str, key: str) -> IdempotencyRecord | None: ...

    @abstractmethod
    async def put(self, record: IdempotencyRecord) -> None:
        """Insert or replace the record for ``(scope, key)``."""
        ...


def fingerprint(*parts: str) -> str:
    """Stable hash of a request's content; length-prefixed, so parts can't run together."""
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode()
        digest.update(len(encoded).to_bytes(4, "big") + encoded)
    return digest.hexdigest()
