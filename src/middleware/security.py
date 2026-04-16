from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Headers sent on every response regardless of environment.
# X-XSS-Protection is intentionally omitted: it was deprecated in 2019 and
# can *introduce* XSS vulnerabilities in legacy IE via its blocking heuristics.
# Modern browsers ignore it; CSP handles XSS protection instead.
_BASE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Only sent in production (HTTPS).  Sending HSTS over plain HTTP (development)
# causes browsers to permanently block future HTTP connections to the same host,
# breaking local development workflows and requiring a manual HSTS reset.
_PROD_ONLY_HEADERS: dict[str, str] = {
    # 2-year max-age satisfies HSTS preload list requirements.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
}

# Production: strict CSP
_CSP_PRODUCTION = "default-src 'self'"

# Development: allow CDN assets required by Swagger UI / ReDoc
_CSP_DEVELOPMENT = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
    "font-src 'self' fonts.gstatic.com; "
    "img-src 'self' data: fastapi.tiangolo.com"
)


class SecurityHeadersMiddleware:
    """Append security-related headers to every HTTP response."""

    def __init__(self, app: ASGIApp, *, production: bool = True) -> None:
        self.app = app
        csp = _CSP_PRODUCTION if production else _CSP_DEVELOPMENT
        headers = {**_BASE_HEADERS, "Content-Security-Policy": csp}
        if production:
            headers.update(_PROD_ONLY_HEADERS)
        self._headers = headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self._headers.items():
                    headers.append(name, value)
            await send(message)

        await self.app(scope, receive, _send)
