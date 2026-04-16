from __future__ import annotations

from audit.backend import AuditBackend, AuditEvent


class MultiAuditBackend(AuditBackend):
    """
    Fan-out audit backend — writes every event to multiple backends in order.

    All backends receive the same event.  If one backend raises, the
    exception propagates immediately and subsequent backends are **not**
    called, so order matters: put the most critical backend first.

    Example::

        from audit.backends.stream import StdoutAuditBackend, StderrAuditBackend
        from audit.backends.multi import MultiAuditBackend

        backend = MultiAuditBackend([
            StdoutAuditBackend(),   # informational stream
            StderrAuditBackend(),   # critical security stream
        ])

    Parameters
    ----------
    backends:
        Ordered list of :class:`~audit.backend.AuditBackend` instances.
    """

    def __init__(self, backends: list[AuditBackend]) -> None:
        self._backends = backends

    async def log(self, event: AuditEvent) -> None:
        for backend in self._backends:
            await backend.log(event)
