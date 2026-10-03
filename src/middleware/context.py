from __future__ import annotations

from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from context import RequestContext, _ctx_var


class RequestContextMiddleware:
    """
    Create a :class:`~blitz.context.RequestContext` for every request.

    The context is stored on ``request.state.ctx`` for use in route handlers
    and is also pushed into the module-level ``ContextVar`` for utility code
    that does not hold a reference to the request.

    Appends an ``X-Request-ID`` header to every response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Reconstruct lightweight header view from raw ASGI scope
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or uuid4().hex

        # Store context on request.state so route handlers can reach it via
        # request.state.ctx.  Go through Request.state rather than scope["state"]
        # directly: under a real ASGI server the latter is the plain lifespan-state
        # dict, which Starlette wraps for attribute access.
        from starlette.requests import Request

        request = Request(scope, receive, send)
        ctx = RequestContext(request=request, request_id=request_id)
        request.state.ctx = ctx

        token = _ctx_var.set(ctx)

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            _ctx_var.reset(token)
