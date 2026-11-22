from audit.backend import AuditBackend, AuditEvent


class RecordingAuditBackend(AuditBackend):
    """Keeps every audit event in memory, for assertions."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        #: Set to make ``log`` raise it (simulates an unavailable audit sink).
        self.fail_with: Exception | None = None

    async def log(self, event: AuditEvent) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.events.append(event)

    def operations(self, name: str) -> list[AuditEvent]:
        """Events recorded by a use case (``"todos.create"``), not the per-request HTTP events."""
        return [e for e in self.events if e.method == name]
