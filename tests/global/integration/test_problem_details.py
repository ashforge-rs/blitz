"""Every framework-produced error uses RFC 9457 application/problem+json."""

import json

from httpx import ASGITransport, AsyncClient

from app import create_app
from audit.backends.noop import NoopAuditBackend
from config import Settings
from errors.problem import PROBLEM_JSON, problem


def _assert_problem(r, status):
    assert r.status_code == status
    assert r.headers["content-type"].startswith(PROBLEM_JSON)
    body = r.json()
    assert body["status"] == status
    assert body["type"] == "about:blank"
    assert isinstance(body["title"], str)
    assert isinstance(body["detail"], str)
    return body


async def test_not_found_route(client):
    body = _assert_problem(await client.get("/v1/nope", headers={"X-Request-ID": "rid-1"}), 404)
    assert body["title"] == "Not Found"
    assert body["instance"] == "/v1/nope"
    assert body["request_id"] == "rid-1"


async def test_validation_error_lists_field_errors(client):
    body = _assert_problem(await client.post("/v1/example/", json={}), 422)
    assert body["detail"] == "Request validation failed"
    assert body["errors"]
    assert body["errors"][0]["loc"][-1] == "name"


async def test_domain_error_includes_code(client):
    body = _assert_problem(await client.get("/v1/example/missing-id"), 404)
    assert body["code"] == "not_found"


async def test_http_exception_headers_preserved(test_settings):
    class _NoCreds:
        async def authenticate(self, request):
            return None

        async def authorize(self, request, principal, ctx):
            return True

    from fastapi import Depends

    from auth.dependency import get_auth_context

    app = create_app(
        settings=test_settings, audit_backend=NoopAuditBackend(), auth_provider=_NoCreds()
    )

    @app.get("/protected")
    async def protected(principal=Depends(get_auth_context)):  # noqa: B008
        return principal

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/protected")
    _assert_problem(r, 401)
    assert r.headers["www-authenticate"] == "Bearer"


async def test_structured_http_exception_detail_goes_to_errors(test_settings):
    from fastapi import HTTPException

    app = create_app(settings=test_settings, audit_backend=NoopAuditBackend())

    @app.get("/structured")
    async def structured():
        raise HTTPException(status_code=409, detail={"field": "email", "reason": "taken"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = _assert_problem(await c.get("/structured"), 409)
    assert body["errors"] == {"field": "email", "reason": "taken"}
    assert body["detail"] == "Conflict"


async def test_rate_limit_is_problem(test_settings):
    settings = Settings(**{**test_settings.model_dump(), "RATE_LIMIT": "1/minute"})
    app = create_app(settings=settings, audit_backend=NoopAuditBackend())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/metrics")
        r = await c.get("/metrics")
    _assert_problem(r, 429)
    assert "retry-after" in r.headers


async def test_size_limit_is_problem(test_settings):
    settings = Settings(**{**test_settings.model_dump(), "MAX_REQUEST_SIZE_BYTES": 10})
    app = create_app(settings=settings, audit_backend=NoopAuditBackend())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        _assert_problem(await c.post("/live", content=b"x" * 100), 413)


def test_streamed_413_body_is_valid_problem():
    from middleware.size_limit import _TOO_LARGE_BODY

    assert json.loads(_TOO_LARGE_BODY) == problem(413, "Request body too large")


def test_problem_defaults_title_and_detail_to_reason_phrase():
    assert problem(503) == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "detail": "Service Unavailable",
    }
