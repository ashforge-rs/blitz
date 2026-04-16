from __future__ import annotations

from fastapi import Depends, Request
from httpx import ASGITransport, AsyncClient

from app import create_app
from audit.backends.noop import NoopAuditBackend
from auth.dependency import get_auth_context
from config import Settings
from context import RequestContext

# ---------------------------------------------------------------------------
# Liveness / readiness
# ---------------------------------------------------------------------------


async def test_liveness(client):
    r = await client.get("/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_no_checks(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_health_failing_check(test_settings):
    async def bad_check():
        return {"name": "db", "healthy": False}

    app = create_app(
        settings=test_settings,
        audit_backend=NoopAuditBackend(),
        health_checks=[bad_check],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


async def test_metrics_endpoint(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# Request context
# ---------------------------------------------------------------------------


async def test_request_id_header(client):
    r = await client.get("/live", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


async def test_request_id_generated(client):
    r = await client.get("/live")
    assert len(r.headers["x-request-id"]) == 32  # UUID4 hex


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


async def test_security_headers(client):
    r = await client.get("/live")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert "x-xss-protection" not in r.headers  # deprecated; removed to avoid IE XSS bypass


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


async def test_rate_limit_exceeded(test_settings):
    settings = Settings(
        **{
            **test_settings.model_dump(),
            "RATE_LIMIT": "1/minute",
        }
    )
    app = create_app(settings=settings, audit_backend=NoopAuditBackend())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Use /metrics (not an exempt path) so the limiter is exercised
        r1 = await c.get("/metrics")
        r2 = await c.get("/metrics")
    # First request passes, second should be rate limited
    assert r1.status_code == 200
    assert r2.status_code == 429
    assert "retry-after" in r2.headers


# ---------------------------------------------------------------------------
# Request size limit
# ---------------------------------------------------------------------------


async def test_size_limit_content_length(test_settings):
    settings = Settings(**{**test_settings.model_dump(), "MAX_REQUEST_SIZE_BYTES": 10})
    app = create_app(settings=settings, audit_backend=NoopAuditBackend())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/live", content=b"x" * 100)
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# Error sanitisation
# ---------------------------------------------------------------------------


async def test_unhandled_exception_prod(test_settings):
    prod_settings = Settings(**{**test_settings.model_dump(), "ENVIRONMENT": "production"})
    boom_app = create_app(settings=prod_settings, audit_backend=NoopAuditBackend())

    @boom_app.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    # Starlette 0.42+ re-raises the exception after calling the error handler so
    # that test cases can optionally observe it.  We don't want that here — we only
    # care that the HTTP response body is sanitised.
    async with AsyncClient(
        transport=ASGITransport(app=boom_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert "secret" not in r.text
    assert "RuntimeError" not in r.text


async def test_unhandled_exception_dev(test_settings):
    dev_settings = Settings(**{**test_settings.model_dump(), "ENVIRONMENT": "development"})
    boom_app = create_app(settings=dev_settings, audit_backend=NoopAuditBackend())

    @boom_app.get("/boom")
    async def boom():
        raise RuntimeError("something went wrong")

    async with AsyncClient(
        transport=ASGITransport(app=boom_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# Auth hooks
# ---------------------------------------------------------------------------


class _AlwaysAllow:
    async def authenticate(self, request: Request) -> dict:
        return {"user": "alice"}

    async def authorize(self, request: Request, principal: dict, context: RequestContext) -> bool:
        return True


class _AlwaysDeny:
    async def authenticate(self, request: Request) -> dict:
        return {"user": "alice"}

    async def authorize(self, request: Request, principal: dict, context: RequestContext) -> bool:
        return False


class _NoCredentials:
    async def authenticate(self, request: Request) -> None:
        return None

    async def authorize(self, request: Request, principal: dict, context: RequestContext) -> bool:
        return True


def _make_auth_app(settings, auth_provider):
    a = create_app(settings=settings, audit_backend=NoopAuditBackend(), auth_provider=auth_provider)

    @a.get("/protected")
    async def protected(principal=Depends(get_auth_context)):  # noqa: B008
        return {"principal": principal}

    return a


async def test_auth_allow(test_settings):
    app = _make_auth_app(test_settings, _AlwaysAllow())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/protected")
    assert r.status_code == 200


async def test_auth_forbidden(test_settings):
    app = _make_auth_app(test_settings, _AlwaysDeny())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/protected")
    assert r.status_code == 403


async def test_auth_unauthorized(test_settings):
    app = _make_auth_app(test_settings, _NoCredentials())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/protected")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Audit dispatch
# ---------------------------------------------------------------------------


async def test_audit_event_dispatched(test_settings):
    events = []

    from audit.backend import AuditBackend, AuditEvent

    class _Collector(AuditBackend):
        async def log(self, event: AuditEvent) -> None:
            events.append(event)

    app = create_app(settings=test_settings, audit_backend=_Collector())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/live")

    assert len(events) == 1
    ev = events[0]
    assert ev.method == "GET"
    assert ev.path == "/live"
    assert ev.status_code == 200
    assert ev.duration_ms is not None and ev.duration_ms > 0
    assert ev.request_id != ""
