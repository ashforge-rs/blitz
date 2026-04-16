from __future__ import annotations

import json
import sys

from audit.backend import AuditBackend, AuditEvent


def _serialize(event: AuditEvent) -> str:
    return json.dumps(
        {
            "timestamp_ns": event.timestamp_ns,
            "event_type": event.event_type,
            "correlation_id": event.correlation_id or event.request_id or None,
            "remote_addr": event.remote_addr or (f"{event.ip}" if event.ip else None),
            "principal": str(event.principal) if event.principal is not None else None,
            "method": event.method,
            "path": event.path,
            "status_code": event.status_code,
            "result": event.result,
            "severity": event.severity,
            "metadata": event.metadata,
            "params": event.params,
            "error": event.error,
        },
        separators=(",", ":"),
    )


class StdoutAuditBackend(AuditBackend):
    """
    Writes JSON-formatted audit events to stdout.

    Suitable for containerised environments where stdout is captured by log
    aggregators (Docker, Kubernetes, AWS CloudWatch, etc.).
    """

    async def log(self, event: AuditEvent) -> None:
        print(_serialize(event), file=sys.stdout, flush=True)


class StderrAuditBackend(AuditBackend):
    """
    Writes JSON-formatted audit events to stderr.

    Useful for separating critical security events from normal application
    output when stdout is used for general logs.
    """

    async def log(self, event: AuditEvent) -> None:
        print(_serialize(event), file=sys.stderr, flush=True)
