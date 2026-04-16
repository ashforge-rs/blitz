from __future__ import annotations

from loguru import logger

from audit.backend import AuditBackend, AuditEvent, AuditSeverity

_SEVERITY_TO_LEVEL = {
    AuditSeverity.INFO: "INFO",
    AuditSeverity.WARNING: "WARNING",
    AuditSeverity.CRITICAL: "CRITICAL",
}


class LoguruAuditBackend(AuditBackend):
    """
    Default audit backend — emits structured JSON via Loguru.

    Log level is driven by :attr:`~audit.backend.AuditEvent.severity`.
    For ``HTTP_REQUEST`` events the HTTP status code also influences the
    level: 5xx → ``ERROR``, 4xx → ``WARNING``, 2xx/3xx → ``INFO``.

    In production (``serialize=True`` Loguru sink) each event becomes a
    single JSON line.  In development it is human-readable.
    """

    async def log(self, event: AuditEvent) -> None:
        from audit.backend import AuditEventType

        # HTTP_REQUEST events: derive level from status code if present
        if event.event_type == AuditEventType.HTTP_REQUEST and event.status_code is not None:
            if event.status_code >= 500:
                level = "ERROR"
            elif event.status_code >= 400:
                level = "WARNING"
            else:
                level = "INFO"
        else:
            level = _SEVERITY_TO_LEVEL.get(event.severity, "INFO")

        logger.bind(
            audit=True,
            event_type=event.event_type,
            timestamp_ns=event.timestamp_ns,
            request_id=event.request_id,
            correlation_id=event.correlation_id,
            method=event.method,
            path=event.path,
            status_code=event.status_code,
            duration_ms=round(event.duration_ms, 2) if event.duration_ms is not None else None,
            ip=event.ip,
            remote_addr=event.remote_addr,
            principal=str(event.principal) if event.principal is not None else None,
            result=event.result,
            severity=event.severity,
            error=event.error,
            metadata=event.metadata,
            **event.extra,
        ).log(level, "AUDIT")
