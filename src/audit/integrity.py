from __future__ import annotations

import hashlib
import json
from threading import Lock

from audit.backend import AuditEvent, AuditIntegrity


class NoIntegrity(AuditIntegrity):
    """
    No-op integrity implementation.

    Use only when integrity is guaranteed externally (e.g. write-once object
    storage, WORM drives) or when the overhead of sequence/checksum
    computation is demonstrably unnecessary.
    """

    def add_integrity(self, event: AuditEvent) -> None:
        pass


class SequenceIntegrity(AuditIntegrity):
    """
    Adds a monotonically increasing ``sequence`` number to every event.

    Sequence numbers allow consumers to detect:

    - **Missing events** — a gap in the sequence (e.g. 41 → 43).
    - **Duplicate events** — the same sequence number appearing twice.
    - **Out-of-order delivery** — numbers arriving in non-monotonic order.

    Thread-safe: the counter is protected by a :class:`threading.Lock`.

    Parameters
    ----------
    start:
        First sequence number to emit (default ``1``).
    """

    def __init__(self, start: int = 1) -> None:
        self._counter = start - 1
        self._lock = Lock()

    def add_integrity(self, event: AuditEvent) -> None:
        with self._lock:
            self._counter += 1
            seq = self._counter
        event.metadata["sequence"] = seq


class ChecksumIntegrity(AuditIntegrity):
    """
    Adds a SHA-256 ``checksum`` of the event's stable fields.

    The checksum covers: ``event_type``, ``timestamp_ns``, ``principal``,
    ``remote_addr``, ``method``, ``path``, ``status_code``, and ``result``.
    This allows consumers to detect post-write tampering of the
    security-relevant fields.

    Parameters
    ----------
    algorithm:
        Any algorithm accepted by :func:`hashlib.new` (default ``"sha256"``).
    """

    def __init__(self, algorithm: str = "sha256") -> None:
        self._algorithm = algorithm

    def add_integrity(self, event: AuditEvent) -> None:
        payload = json.dumps(
            {
                "event_type": event.event_type,
                "timestamp_ns": event.timestamp_ns,
                "principal": str(event.principal) if event.principal is not None else None,
                "remote_addr": event.remote_addr,
                "method": event.method,
                "path": event.path,
                "status_code": event.status_code,
                "result": event.result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.new(self._algorithm, payload.encode()).hexdigest()
        event.metadata["checksum"] = f"{self._algorithm}:{digest}"


class CombinedIntegrity(AuditIntegrity):
    """
    Apply multiple :class:`AuditIntegrity` implementations in order.

    Example::

        integrity = CombinedIntegrity([
            SequenceIntegrity(),
            ChecksumIntegrity(),
        ])

    Parameters
    ----------
    mechanisms:
        Ordered list of integrity implementations.  Each is applied in turn
        so later mechanisms can include earlier metadata (e.g. ``checksum``
        can include the ``sequence`` added by ``SequenceIntegrity``).
    """

    def __init__(self, mechanisms: list[AuditIntegrity]) -> None:
        self._mechanisms = mechanisms

    def add_integrity(self, event: AuditEvent) -> None:
        for mechanism in self._mechanisms:
            mechanism.add_integrity(event)
