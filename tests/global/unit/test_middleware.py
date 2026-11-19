"""Unit tests for the ASGI middleware, driven with raw ASGI scope/receive/send."""

from __future__ import annotations

import asyncio
import ipaddress
import time

import pytest
from limits.aio.storage import MemoryStorage
from starlette.requests import Request

from middleware.context import _request_id_from
from middleware.rate_limit import RateLimitMiddleware, _resolve_ip
from middleware.size_limit import RequestSizeLimitMiddleware
from middleware.timeout import TimeoutMiddleware


def _scope(headers=(), path="/x", client=("1.2.3.4", 1234)):
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(k.lower(), v) for k, v in headers],
        "client": client,
        "query_string": b"",
    }


async def _call(app, scope, body_chunks=(b"",)):
    chunks = list(body_chunks)
    sent: list[dict] = []

    async def receive():
        body = chunks.pop(0) if chunks else b""
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _statuses(sent):
    return [m["status"] for m in sent if m["type"] == "http.response.start"]


async def _ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


# ---------------------------------------------------------------------------
# TimeoutMiddleware
# ---------------------------------------------------------------------------


async def test_timeout_before_response_returns_504():
    async def slow(scope, receive, send):
        await asyncio.sleep(1)

    sent = await _call(TimeoutMiddleware(slow, timeout_seconds=0.01), _scope())
    assert _statuses(sent) == [504]


async def test_timeout_after_response_started_reraises_without_second_start():
    async def slow_stream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await asyncio.sleep(1)

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    with pytest.raises(TimeoutError):
        await TimeoutMiddleware(slow_stream, timeout_seconds=0.01)(_scope(), receive, send)
    assert _statuses(sent) == [200]  # no protocol-violating second response.start


# ---------------------------------------------------------------------------
# RequestSizeLimitMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [b"abc", b"-1", b"1.5", b""])
async def test_size_limit_rejects_malformed_content_length(value):
    sent = await _call(RequestSizeLimitMiddleware(_ok), _scope([(b"content-length", value)]))
    assert _statuses(sent) == [400]


async def test_size_limit_streamed_body_sends_single_413():
    async def echo_chunks(scope, receive, send):
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"a", "more_body": True})
        await send({"type": "http.response.body", "body": b"b"})

    app = RequestSizeLimitMiddleware(echo_chunks, max_bytes=4)
    sent = await _call(app, _scope(), body_chunks=[b"xxx", b"xxx"])
    assert _statuses(sent) == [413]
    assert len([m for m in sent if m["type"] == "http.response.body"]) == 1


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------


async def test_rate_limit_retry_after_is_seconds_not_epoch():
    app = RateLimitMiddleware(_ok, rate_limit="1/minute", storage=MemoryStorage())
    await _call(app, _scope())
    sent = await _call(app, _scope())
    assert _statuses(sent) == [429]
    headers = dict(sent[0]["headers"])
    retry_after = int(headers[b"retry-after"])
    assert 1 <= retry_after <= 60
    assert retry_after < time.time()  # sanity: not an epoch timestamp


async def test_rate_limit_fails_open_on_storage_error():
    class _Broken(MemoryStorage):
        async def acquire_entry(self, *args, **kwargs):
            raise ConnectionError("storage down")

    app = RateLimitMiddleware(_ok, rate_limit="1/minute", storage=_Broken())
    assert _statuses(await _call(app, _scope())) == [200]
    assert _statuses(await _call(app, _scope())) == [200]


def _req(peer, xff=None):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request(_scope(headers, client=(peer, 1)))


_PROXIES = (ipaddress.ip_network("10.0.0.0/8"),)


def test_resolve_ip_ignores_xff_from_untrusted_peer():
    assert _resolve_ip(_req("1.2.3.4", "6.6.6.6"), _PROXIES) == "1.2.3.4"


def test_resolve_ip_walks_xff_right_to_left_from_trusted_peer():
    # Client spoofs 6.6.6.6 at the front; the real client is 5.5.5.5.
    assert _resolve_ip(_req("10.0.0.1", "6.6.6.6, 5.5.5.5, 10.0.0.2"), _PROXIES) == "5.5.5.5"


def test_resolve_ip_skips_garbage_xff_entries():
    assert _resolve_ip(_req("10.0.0.1", "5.5.5.5, not-an-ip"), _PROXIES) == "5.5.5.5"


def test_trusted_proxies_wired_from_settings(test_settings):
    from app import create_app
    from config import Settings

    settings = Settings(**{**test_settings.model_dump(), "TRUSTED_PROXIES": ["10.0.0.0/8"]})
    app = create_app(settings=settings)
    limiter = next(m for m in app.user_middleware if m.cls is RateLimitMiddleware)
    assert limiter.kwargs["trusted_proxies"] == ["10.0.0.0/8"]


# ---------------------------------------------------------------------------
# Request ID validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [b"abc123", b"0f8fad5b-d9cb-469f-a165-70867728950e", b"a.b:c_d"])
def test_request_id_accepts_safe_values(value):
    assert _request_id_from(value) == value.decode()


@pytest.mark.parametrize(
    "value", [b"", b"x" * 129, b"evil\nINFO forged log line", b"has space", "é".encode()]
)
def test_request_id_replaces_unsafe_values(value):
    rid = _request_id_from(value)
    assert rid != value.decode(errors="replace")
    assert len(rid) == 32
