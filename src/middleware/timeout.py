from __future__ import annotations

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class TimeoutMiddleware:
    """
    Enforce a per-request wall-clock timeout.

    Wraps the entire ASGI request-response cycle in ``asyncio.wait_for``.
    Returns 504 if the timeout expires before the handler completes.

    Note: for streaming responses the timeout covers the full stream.
    """

    def __init__(self, app: ASGIApp, timeout_seconds: float = 30.0) -> None:
        self.app = app
        self.timeout = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send),
                timeout=self.timeout,
            )
        except TimeoutError:
            response = JSONResponse({"detail": "Request timed out"}, status_code=504)
            await response(scope, receive, send)
