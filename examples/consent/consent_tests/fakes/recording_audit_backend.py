from audit.backend import AuditBackend, AuditEvent


class RecordingAuditBackend(AuditBackend):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        self.fail_with: Exception | None = None

    async def log(self, event: AuditEvent) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.events.append(event)

    def operations(self, prefix: str) -> list[AuditEvent]:
        return [e for e in self.events if (e.method or "").startswith(prefix)]
