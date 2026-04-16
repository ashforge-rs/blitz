from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from audit.backend import AuditEvent, AuditEventType, AuditResult, AuditSeverity
from middleware.rate_limit import _resolve_ip


class AuditMiddleware:
    """
    Dispatch an :class:`~audit.backend.AuditEvent` after every HTTP request.

    Runs just inside the outermost ``_InFlightMiddleware`` so it captures all
    requests that pass the in-flight gate. Reads the resolved ``principal``
    from ``request.state.ctx`` (set by the auth dependency if used).

    The backend is read from ``app.state.audit_backend`` at request time, so
    the backend can be replaced on the live app if needed.

    If ``app.state.audit_integrity`` is set it is applied to every event
    before the backend receives it, adding sequence numbers and/or checksums.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def _send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            app_obj = scope.get("app")
            audit_backend = (
                getattr(app_obj.state, "audit_backend", None) if app_obj is not None else None
            )
            if audit_backend is not None:
                assert app_obj is not None
                app_settings = getattr(app_obj.state, "settings", None)
                trusted = frozenset(app_settings.TRUSTED_PROXIES if app_settings else [])

                from starlette.requests import Request

                request = Request(scope)
                ctx = getattr(scope.get("state"), "ctx", None)

                client_ip = _resolve_ip(request, trusted)
                client = request.client
                remote_addr = f"{client.host}:{client.port}" if client else client_ip

                result = AuditResult.SUCCESS
                severity = AuditSeverity.INFO
                if status_code >= 500:
                    result = AuditResult.FAILURE
                    severity = AuditSeverity.WARNING
                elif status_code == 403:
                    result = AuditResult.DENIED
                    severity = AuditSeverity.CRITICAL
                elif status_code == 401:
                    result = AuditResult.DENIED
                    severity = AuditSeverity.WARNING
                elif status_code >= 400:
                    result = AuditResult.FAILURE

                principal = ctx.get("principal") if ctx else None
                request_id = ctx.request_id if ctx else ""

                event = AuditEvent(
                    event_type=AuditEventType.HTTP_REQUEST,
                    severity=severity,
                    result=result,
                    # HTTP-specific
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    # Identity
                    principal=principal,
                    remote_addr=remote_addr,
                    ip=client_ip,
                    correlation_id=request_id,
                    # Backward compat
                    request_id=request_id,
                )

                integrity = getattr(app_obj.state, "audit_integrity", None)
                if integrity is not None:
                    integrity.add_integrity(event)

                await audit_backend.log(event)
