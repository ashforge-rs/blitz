from __future__ import annotations

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class TimeoutMiddleware:
    """
    Enforce a per-request wall-clock timeout.

    Wraps the entire ASGI request-response cycle in ``asyncio.wait_for``.

    - Timeout **before** the response has started → ``504`` JSON response.
    - Timeout **after** the response has started (e.g. a slow streaming body)
      → the ``TimeoutError`` is re-raised.  The status line has already been
      sent, so a 504 can no longer be delivered; re-raising lets the server
      abort the connection instead of emitting a second, protocol-violating
      ``http.response.start``.
    """

    def __init__(self, app: ASGIApp, timeout_seconds: float = 30.0) -> None:
        self.app = app
        self.timeout = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(self.app(scope, receive, _send), timeout=self.timeout)
        except TimeoutError:
            if response_started:
                raise
            response = JSONResponse({"detail": "Request timed out"}, status_code=504)
            await response(scope, receive, send)
