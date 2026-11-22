"""
Convenience helpers for emitting common security audit events.

These functions construct a fully-populated :class:`~audit.backend.AuditEvent`,
apply integrity metadata, and dispatch it to a backend — all in one call.
They are the Python equivalent of the ``log_security_violation`` and
``log_auth_event`` helpers from the Rust implementation.

Example::

    from audit.helpers import log_security_violation

    await log_security_violation(
        backend=request.app.state.audit_backend,
        integrity=request.app.state.audit_integrity,
        violation_type="rate_limit_exceeded",
        remote_addr="192.0.2.1:54321",
        principal="user@example.com",
    )
"""

from typing import TYPE_CHECKING, Any

from audit.backend import (
    AuditBackend,
    AuditEvent,
    AuditEventType,
    AuditIntegrity,
    AuditResult,
    AuditSeverity,
)

if TYPE_CHECKING:
    from context import RequestContext


async def log_security_violation(
    backend: AuditBackend,
    integrity: AuditIntegrity,
    violation_type: str,
    *,
    remote_addr: str | None = None,
    principal: Any = None,
    method: str | None = None,
    path: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """
    Emit a ``SECURITY_VIOLATION`` event at ``CRITICAL`` severity.

    Parameters
    ----------
    backend:
        The :class:`~audit.backend.AuditBackend` to write to.
    integrity:
        The :class:`~audit.backend.AuditIntegrity` to apply before writing.
    violation_type:
        Machine-readable description of the violation, e.g.
        ``"rate_limit_exceeded"``, ``"banned_ip_connection"``,
        ``"request_size_limit_exceeded"``.
    remote_addr:
        ``"host:port"`` of the offending client.
    principal:
        Authenticated identity of the client, if known.
    method:
        HTTP verb or RPC method associated with the violation.
    path:
        URL path associated with the violation.
    extra_metadata:
        Additional key-value pairs merged into ``event.metadata``.
    """
    metadata: dict[str, Any] = {"violation_type": violation_type}
    if extra_metadata:
        metadata.update(extra_metadata)

    event = AuditEvent(
        event_type=AuditEventType.SECURITY_VIOLATION,
        severity=AuditSeverity.CRITICAL,
        result=AuditResult.VIOLATION,
        remote_addr=remote_addr,
        principal=principal,
        method=method,
        path=path,
        metadata=metadata,
    )
    integrity.add_integrity(event)
    await backend.log(event)


async def log_auth_event(
    backend: AuditBackend,
    integrity: AuditIntegrity,
    method: str,
    *,
    remote_addr: str | None = None,
    principal: Any = None,
    allowed: bool,
    event_type: AuditEventType = AuditEventType.AUTHORIZATION_CHECK,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """
    Emit an authentication or authorization audit event.

    Parameters
    ----------
    backend:
        The :class:`~audit.backend.AuditBackend` to write to.
    integrity:
        The :class:`~audit.backend.AuditIntegrity` to apply before writing.
    method:
        The HTTP path or RPC method being accessed.
    remote_addr:
        ``"host:port"`` of the client.
    principal:
        Authenticated identity of the client, if known.
    allowed:
        ``True`` if the request was permitted; ``False`` if denied.
    event_type:
        Defaults to ``AUTHORIZATION_CHECK``; pass
        ``AuditEventType.AUTHENTICATION_ATTEMPT`` for login events.
    extra_metadata:
        Additional key-value pairs merged into ``event.metadata``.
    """
    result = AuditResult.SUCCESS if allowed else AuditResult.DENIED
    severity = AuditSeverity.INFO if allowed else AuditSeverity.CRITICAL

    metadata: dict[str, Any] = {}
    if extra_metadata:
        metadata.update(extra_metadata)

    event = AuditEvent(
        event_type=event_type,
        severity=severity,
        result=result,
        remote_addr=remote_addr,
        principal=principal,
        method=method,
        metadata=metadata,
    )
    integrity.add_integrity(event)
    await backend.log(event)


async def log_operation(
    backend: AuditBackend,
    integrity: AuditIntegrity,
    ctx: RequestContext,
    operation: str,
    *,
    result: AuditResult = AuditResult.SUCCESS,
    resource_id: str | None = None,
    event_type: AuditEventType = AuditEventType.ADMIN_ACTION,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """
    Emit an audit event for a state-changing domain operation.

    Principal, client address, request ID and path are taken from *ctx*, so a
    service only names the operation (e.g. ``"orders.create"``) and its outcome.
    Non-success results are logged at ``WARNING`` severity.

    Parameters
    ----------
    ctx:
        The current :class:`~context.RequestContext`.
    operation:
        Dotted operation name, recorded as ``event.method`` and in metadata.
    result:
        Outcome of the operation; defaults to ``SUCCESS``.
    resource_id:
        Identifier of the affected record, recorded as ``metadata["resource_id"]``.
    extra_metadata:
        Additional key-value pairs merged into ``event.metadata``.
    """
    metadata: dict[str, Any] = {"operation": operation}
    if resource_id is not None:
        metadata["resource_id"] = resource_id
    if extra_metadata:
        metadata.update(extra_metadata)

    event = AuditEvent(
        event_type=event_type,
        severity=AuditSeverity.INFO if result == AuditResult.SUCCESS else AuditSeverity.WARNING,
        result=result,
        principal=ctx.get("principal"),
        remote_addr=ctx.remote_addr,
        correlation_id=ctx.request_id,
        method=operation,
        path=ctx.path,
        metadata=metadata,
    )
    integrity.add_integrity(event)
    await backend.log(event)
