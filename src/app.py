from __future__ import annotations

import types
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import FastAPI
from limits.storage import MemoryStorage, Storage

from audit.backend import AuditBackend, AuditIntegrity
from audit.backends.loguru import LoguruAuditBackend
from audit.integrity import NoIntegrity
from auth.protocol import AuthProvider
from config import Settings, get_settings
from errors.handlers import register_error_handlers
from lifespan import lifespan
from middleware.stack import register_middleware
from routes import health, metrics

HealthCheckFn = Callable[[], Coroutine[Any, Any, dict[str, Any]]]


def create_app(
    *,
    settings: Settings | None = None,
    auth_provider: AuthProvider | None = None,
    audit_backend: AuditBackend | None = None,
    audit_integrity: AuditIntegrity | None = None,
    rate_limit_storage: Storage | None = None,
    health_checks: list[HealthCheckFn] | None = None,
    domains: list[types.ModuleType] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> FastAPI:
    """
    Create and return a fully configured FastAPI application.

    Parameters
    ----------
    settings:
        Overrides the global ``Settings`` instance.  Defaults to reading from
        environment variables / ``.env``.
    auth_provider:
        An object implementing the :class:`~auth.protocol.AuthProvider`
        protocol.  When ``None`` the ``get_auth_context`` dependency is a no-op.
    audit_backend:
        An :class:`~audit.backend.AuditBackend` implementation.
        Defaults to :class:`~audit.backends.loguru.LoguruAuditBackend`.
    audit_integrity:
        An :class:`~audit.backend.AuditIntegrity` implementation that adds
        tamper-evidence metadata (sequence numbers, checksums) to every event
        before it reaches the backend.  Defaults to
        :class:`~audit.integrity.NoIntegrity` (no-op).  For production
        deployments that require compliance audit trails consider
        :class:`~audit.integrity.SequenceIntegrity` or
        :class:`~audit.integrity.CombinedIntegrity`.
    rate_limit_storage:
        A :class:`limits.storage.Storage` implementation used by the rate
        limiter.  Defaults to :class:`limits.storage.MemoryStorage` (in-process,
        single-worker).  Pass any ``limits``-compatible storage backend to share
        state across workers — for example a custom ``RedisStorage``,
        ``MemcachedStorage``, or your own implementation.
    health_checks:
        A list of async callables each returning a dict with at least
        ``{"name": str, "healthy": bool}``.
    domains:
        A list of domain modules, each exposing:

        - ``make_router() -> APIRouter`` — called once at app-creation time;
          returns the router with all routes for this domain.
        - ``async bootstrap(settings: Settings, **kwargs) -> Any`` — called
          during lifespan startup; initialise DB pools, clients, etc. and return
          the domain instance.  The instance is stored on
          ``app.state.domains[module.__name__]`` for use in route handlers.
    extra_context:
        Arbitrary key-value pairs stored on ``app.state`` for use across the
        application (e.g. database pools, feature flag clients).
    """
    if settings is None:
        settings = get_settings()

    is_prod = settings.ENVIRONMENT == "production"

    # Build optional OpenAPI contact / license blocks only when values are set
    contact: dict[str, str] | None = None
    has_contact = (
        settings.OPENAPI_CONTACT_NAME
        or settings.OPENAPI_CONTACT_EMAIL
        or settings.OPENAPI_CONTACT_URL
    )
    if has_contact:
        contact = {}
        if settings.OPENAPI_CONTACT_NAME:
            contact["name"] = settings.OPENAPI_CONTACT_NAME
        if settings.OPENAPI_CONTACT_EMAIL:
            contact["email"] = settings.OPENAPI_CONTACT_EMAIL
        if settings.OPENAPI_CONTACT_URL:
            contact["url"] = settings.OPENAPI_CONTACT_URL

    license_info: dict[str, str] | None = None
    if settings.OPENAPI_LICENSE_NAME:
        license_info = {"name": settings.OPENAPI_LICENSE_NAME}
        if settings.OPENAPI_LICENSE_URL:
            license_info["url"] = settings.OPENAPI_LICENSE_URL

    servers: list[dict[str, str]] | None = (
        [{"url": s} for s in settings.OPENAPI_SERVERS] if settings.OPENAPI_SERVERS else None
    )

    app = FastAPI(
        title=settings.OPENAPI_TITLE,
        description=settings.OPENAPI_DESCRIPTION,
        version=settings.OPENAPI_VERSION,
        contact=contact,
        license_info=license_info,
        servers=servers,
        lifespan=lifespan,
        # Hide interactive docs + schema in production
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # --- App state ---
    app.state.settings = settings
    app.state.auth_provider = auth_provider
    app.state.audit_backend = audit_backend if audit_backend is not None else LoguruAuditBackend()
    app.state.audit_integrity = audit_integrity if audit_integrity is not None else NoIntegrity()
    app.state.health_checks = health_checks or []
    app.state.metrics_require_auth = settings.METRICS_REQUIRE_AUTH
    app.state.in_flight = 0
    app.state.domains = {}
    app.state._domain_modules = domains or []

    if extra_context:
        for key, value in extra_context.items():
            setattr(app.state, key, value)

    # --- Middleware (order defined in stack.py) ---
    register_middleware(app, settings, rate_limit_storage=rate_limit_storage or MemoryStorage())

    # --- Exception handlers ---
    register_error_handlers(app, is_production=is_prod)

    # --- Prometheus auto-instrumentation ---
    if settings.METRICS_ENDPOINT_ENABLED:
        try:
            from prometheus_fastapi_instrumentator import Instrumentator

            Instrumentator().instrument(app)
        except Exception:
            pass  # Already registered (e.g. multiple create_app() calls in tests)

    # --- Built-in routes ---
    app.include_router(health.router)
    if settings.METRICS_ENDPOINT_ENABLED:
        app.include_router(metrics.router)

    # --- Domain routes (registered at app-creation time so OpenAPI schema is complete) ---
    for domain_module in app.state._domain_modules:
        if hasattr(domain_module, "make_router"):
            app.include_router(domain_module.make_router())
        if hasattr(domain_module, "register_exception_handlers"):
            domain_module.register_exception_handlers(app)

    # --- OpenTelemetry FastAPI instrumentation ---
    # Instrument after routes are registered so span names resolve to route paths.
    # setup_telemetry() (called in lifespan startup) sets the global TracerProvider
    # before any requests arrive; this call patches the middleware to create spans.
    if settings.OTEL_ENABLED:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except Exception:
            pass  # Already instrumented (e.g. multiple create_app() calls in tests)

    return app
