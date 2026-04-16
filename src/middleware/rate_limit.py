from __future__ import annotations

import ipaddress

from limits import RateLimitItem, parse
from limits.storage import MemoryStorage, Storage
from limits.strategies import MovingWindowRateLimiter
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_ALWAYS_EXEMPT: frozenset[str] = frozenset()


def _resolve_ip(request: Request, trusted_proxies: frozenset[str]) -> str:
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

    if peer and trusted_proxies:
        try:
            peer_addr = ipaddress.ip_address(peer)
        except ValueError:
            return peer or "unknown"

        in_trusted = any(
            peer_addr in ipaddress.ip_network(cidr, strict=False) for cidr in trusted_proxies
        )
        if in_trusted:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                ips = [ip.strip() for ip in forwarded.split(",")]
                # Walk right-to-left: skip known trusted hops to reach the real client.
                for ip in reversed(ips):
                    try:
                        addr = ipaddress.ip_address(ip)
                        if not any(
                            addr in ipaddress.ip_network(cidr, strict=False)
                            for cidr in trusted_proxies
                        ):
                            return ip
                    except ValueError:
                        continue
                # All hops are within trusted ranges (internal cluster); use
                # leftmost as best-effort rather than falling back to the proxy.
                return ips[0]

    return peer or "unknown"


class RateLimitMiddleware:
    """
    Moving-window rate limiter keyed by client IP.

    Defaults to in-memory storage; pass a ``Storage`` instance for distributed
    rate limiting across multiple workers.

    Returns 429 with a ``Retry-After`` header when the limit is exceeded.
    Paths listed in *exempt_paths* (e.g. ``/live``, ``/health``) are skipped.
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
        self._trusted: frozenset[str] = frozenset(trusted_proxies or [])
        self._exempt: frozenset[str] = frozenset(exempt_paths or [])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exempt:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        key = _resolve_ip(request, self._trusted)
        if not self._limiter.hit(self._limit, key):
            try:
                stats = self._limiter.get_window_stats(self._limit, key)
                retry_after = str(max(1, int(stats.reset_time)))
            except Exception:
                retry_after = "60"
            response = JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": retry_after},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
