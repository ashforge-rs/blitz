from __future__ import annotations

import ipaddress
import math
import time
from functools import lru_cache

from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage, Storage
from limits.aio.strategies import MovingWindowRateLimiter
from loguru import logger
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

type _Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=8)
def parse_networks(cidrs: tuple[str, ...]) -> tuple[_Network, ...]:
    """Parse trusted-proxy CIDRs (cached; raises ``ValueError`` on bad input)."""
    return tuple(ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def _is_trusted(ip: str, networks: tuple[_Network, ...]) -> bool | None:
    """``True``/``False`` for a valid IP, ``None`` if *ip* is not an IP address."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    return any(addr in net for net in networks)


def _resolve_ip(request: Request, trusted_proxies: tuple[_Network, ...]) -> str:
    """
    Return the real client IP.

    When the direct peer is within *trusted_proxies*, walks the
    ``X-Forwarded-For`` chain **right-to-left**, skipping every address that
    belongs to a trusted proxy, and returns the first untrusted address — the
    genuine client IP.

    This prevents clients from injecting arbitrary IPs at the front of the XFF
    header to bypass rate limiting (a common attack against naïve
    ``split(",")[0]`` implementations).  A purely leftmost approach is only
    safe when you trust every intermediate proxy in the chain.
    """
    peer = request.client.host if request.client else None
    if not peer:
        return "unknown"
    if not trusted_proxies or not _is_trusted(peer, trusted_proxies):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer

    ips = [ip.strip() for ip in forwarded.split(",")]
    # Walk right-to-left: skip known trusted hops to reach the real client.
    for ip in reversed(ips):
        if _is_trusted(ip, trusted_proxies) is False:
            return ip
    # All hops are within trusted ranges (internal cluster); use leftmost as
    # best-effort rather than falling back to the proxy.
    return ips[0]


class RateLimitMiddleware:
    """
    Moving-window rate limiter keyed by client IP.

    Uses the **async** ``limits.aio`` API so network-backed storages (Redis,
    Memcached, MongoDB) never block the event loop.  Defaults to in-memory
    storage; pass a ``limits.aio.storage.Storage`` instance for distributed
    rate limiting across multiple workers.

    Returns 429 with a ``Retry-After`` header (seconds) when the limit is
    exceeded.  Paths listed in *exempt_paths* (e.g. ``/live``, ``/health``) are
    skipped.  If the storage backend errors, the request is allowed through
    (fail-open) and a warning is logged — an outage of the limiter's backing
    store should not take the whole API down.
    """

    def __init__(
        self,
        app: ASGIApp,
        rate_limit: str = "100/minute",
        storage: Storage | None = None,
        trusted_proxies: list[str] | None = None,
        exempt_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self._storage = storage or MemoryStorage()
        self._limiter = MovingWindowRateLimiter(self._storage)
        self._limit: RateLimitItem = parse(rate_limit)
        self._trusted = parse_networks(tuple(trusted_proxies or ()))
        self._exempt: frozenset[str] = frozenset(exempt_paths or [])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "") in self._exempt:
            await self.app(scope, receive, send)
            return

        key = _resolve_ip(Request(scope), self._trusted)
        try:
            allowed = await self._limiter.hit(self._limit, key)
        except Exception as exc:
            logger.warning("rate limiter storage error — allowing request", error=str(exc))
            allowed = True

        if allowed:
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"detail": "Too many requests"},
            status_code=429,
            headers={"Retry-After": await self._retry_after(key)},
        )
        await response(scope, receive, send)

    async def _retry_after(self, key: str) -> str:
        """Seconds until the window frees a slot (``reset_time`` is an epoch timestamp)."""
        try:
            stats = await self._limiter.get_window_stats(self._limit, key)
        except Exception:
            return str(self._limit.get_expiry())
        return str(max(1, math.ceil(stats.reset_time - time.time())))
