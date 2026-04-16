from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AuditEventType(StrEnum):
    """Classification of the security-significant event being recorded."""

    CONNECTION_ESTABLISHED = "connection_established"
    CONNECTION_CLOSED = "connection_closed"
    AUTHENTICATION_ATTEMPT = "authentication_attempt"
    AUTHORIZATION_CHECK = "authorization_check"
    HTTP_REQUEST = "http_request"
    ERROR_OCCURRED = "error_occurred"
    SECURITY_VIOLATION = "security_violation"
    CONFIGURATION_CHANGE = "configuration_change"
    ADMIN_ACTION = "admin_action"


class AuditResult(StrEnum):
    """Outcome of the audited operation."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    VIOLATION = "violation"


class AuditSeverity(StrEnum):
    """Severity level of the audited event."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(kw_only=True)
class AuditEvent:
    """
    Structured, tamper-evident record of a single security-significant event.

    All fields are keyword-only. Integrity metadata (sequence numbers,
    checksums) is stored in :attr:`metadata` by :class:`~audit.integrity.AuditIntegrity`
    implementations before the event reaches a backend.

    Fields
    ------
    event_type:
        Classification of what happened.
    timestamp_ns:
        Nanosecond-precision Unix timestamp (``time.time_ns()``).  Suitable
        for ordering events within the same second.
    severity:
        Event severity — ``INFO``, ``WARNING``, or ``CRITICAL``.
    result:
        Outcome of the operation — ``SUCCESS``, ``FAILURE``, ``DENIED``, or
        ``VIOLATION``.
    principal:
        Authenticated identity (user ID, API key, client cert subject, …).
        ``None`` when unauthenticated.
    remote_addr:
        ``"host:port"`` string of the immediate client. ``None`` when not
        applicable (e.g. background tasks).
    correlation_id:
        Request / trace ID that ties a chain of events together.
    method:
        HTTP verb (``GET``, ``POST``, …) for HTTP events; RPC method name for
        service events.
    path:
        URL path for HTTP events.
    status_code:
        HTTP response status for HTTP events.
    duration_ms:
        Request processing time in milliseconds for HTTP events.
    ip:
        Client IP address (without port). Kept for backward compatibility;
        prefer :attr:`remote_addr` for new code.
    request_id:
        Request identifier. Kept for backward compatibility; same as
        :attr:`correlation_id`.
    error:
        Human-readable error description when :attr:`result` is ``FAILURE``.
    params:
        Sanitized subset of request parameters. **Never** store raw sensitive
        values (passwords, PII, secrets) here.
    metadata:
        Extensible key-value bag. Integrity mechanisms store ``sequence`` and
        ``checksum`` entries here.
    extra:
        Application-specific fields not covered by the schema above.
    """

    # --- Core ---
    event_type: AuditEventType = AuditEventType.HTTP_REQUEST
    timestamp_ns: int = field(default_factory=time.time_ns)
    severity: AuditSeverity = AuditSeverity.INFO
    result: AuditResult = AuditResult.SUCCESS

    # --- Identity ---
    principal: Any = None
    remote_addr: str | None = None
    correlation_id: str | None = None

    # --- HTTP / RPC detail ---
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    error: str | None = None
    params: Any = None

    # --- Integrity & extensions ---
    metadata: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    # --- Backward-compatible aliases ---
    request_id: str = ""
    ip: str | None = None


class AuditBackend(ABC):
    """
    Base class for audit log backends.

    Implement :meth:`log` and pass an instance to ``create_app(audit_backend=...)``.
    The :meth:`log` method is **intentionally synchronous** from the caller's
    perspective via ``await`` — backends must write before returning so that
    events are never silently dropped on crashes.
    """

    @abstractmethod
    async def log(self, event: AuditEvent) -> None:
        """Persist or forward the audit event."""
        ...


class AuditIntegrity(ABC):
    """
    Adds tamper-evidence fields to an :class:`AuditEvent` before it is logged.

    Implementations mutate ``event.metadata`` in-place by adding entries such
    as ``sequence`` or ``checksum``.  Call :meth:`add_integrity` on every
    event after constructing it and *before* passing it to a backend::

        integrity.add_integrity(event)
        await backend.log(event)
    """

    @abstractmethod
    def add_integrity(self, event: AuditEvent) -> None:
        """Mutate *event* to add integrity metadata."""
        ...
