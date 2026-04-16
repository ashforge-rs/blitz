from __future__ import annotations

from fastapi import FastAPI
from limits.storage import Storage
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from config import Settings
from middleware.audit import AuditMiddleware
from middleware.context import RequestContextMiddleware
from middleware.rate_limit import RateLimitMiddleware
from middleware.security import SecurityHeadersMiddleware
from middleware.size_limit import RequestSizeLimitMiddleware
from middleware.timeout import TimeoutMiddleware


class _InFlightMiddleware:
    """Track the number of in-progress requests for graceful shutdown."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        app_obj = scope.get("app")
        app_state = app_obj.state if app_obj is not None else None
        if app_state is not None:
            app_state.in_flight = getattr(app_state, "in_flight", 0) + 1
        try:
            await self.app(scope, receive, send)
        finally:
            if app_state is not None:
                app_state.in_flight = max(0, getattr(app_state, "in_flight", 1) - 1)


def register_middleware(app: FastAPI, settings: Settings, *, rate_limit_storage: Storage) -> None:
    """
    Register all middleware in the correct Starlette LIFO order.

    Execution order (outermost → innermost):
      TrustedHost → CORS → InFlight → Audit → SecurityHeaders →
      Timeout → SizeLimit → RateLimit → Context → Handler
    """
    # Added first = innermost (executed last before the handler)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        rate_limit=settings.RATE_LIMIT,
        storage=rate_limit_storage,
        exempt_paths={"/live", "/health"},
    )
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_SIZE_BYTES)
    app.add_middleware(TimeoutMiddleware, timeout_seconds=settings.REQUEST_TIMEOUT_SECONDS)
    app.add_middleware(SecurityHeadersMiddleware, production=settings.ENVIRONMENT == "production")
    app.add_middleware(AuditMiddleware)
    app.add_middleware(_InFlightMiddleware)
    # CORS — must sit outside InFlight so preflight OPTIONS are handled cheaply
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # TrustedHost — outermost; rejects bad Host headers before anything else runs
    if settings.ALLOWED_HOSTS:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
