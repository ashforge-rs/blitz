import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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


class IdempotencyKeyTakenError(Exception):
    """:meth:`IdempotencyStore.add` lost a race: a concurrent request committed this key first."""


class IdempotencyStore(ABC):
    """Port: completed requests by ``(scope, key)``, inside the current unit of work."""

    @abstractmethod
    async def get(self, scope: str, key: str) -> IdempotencyRecord | None: ...

    @abstractmethod
    async def add(self, record: IdempotencyRecord) -> None:
        """Record a new key; raise :class:`IdempotencyKeyTakenError` if it already exists."""
        ...

    @abstractmethod
    async def replace(self, record: IdempotencyRecord) -> None:
        """Overwrite the record of an existing key (e.g. a rotated secret reference)."""
        ...


def fingerprint(*parts: str) -> str:
    """Stable hash of a request's content; length-prefixed, so parts can't run together."""
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode()
        digest.update(len(encoded).to_bytes(4, "big") + encoded)
    return digest.hexdigest()


async def retry_once_on_key_race[T](attempt: Callable[[], Awaitable[T]]) -> T:
    """Run a unit of work; if a concurrent request committed the same key first, run it again.

    The losing attempt rolled back, so the second run finds the winner's record
    and replays its result.
    """
    try:
        return await attempt()
    except IdempotencyKeyTakenError:
        return await attempt()
