from __future__ import annotations

from audit.backend import AuditBackend, AuditEvent


class NoopAuditBackend(AuditBackend):
    """Silently discards every audit event. Useful in tests."""

    async def log(self, event: AuditEvent) -> None:
        pass
