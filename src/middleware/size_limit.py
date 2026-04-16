from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestSizeLimitMiddleware:
    """
    Reject requests whose body exceeds *max_bytes*.

    Uses the ``Content-Length`` header for a fast early rejection.
    Chunked-encoded requests without ``Content-Length`` are rejected once the
    accumulated body bytes exceed the limit.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: Content-Length header present
        headers = dict(scope.get("headers", []))
        raw_cl = headers.get(b"content-length")
        if raw_cl is not None and int(raw_cl) > self.max_bytes:
            response = JSONResponse({"detail": "Request body too large"}, status_code=413)
            await response(scope, receive, send)
            return

        # Slow path: count streamed bytes; raise a flag if limit is exceeded
        received: int = 0
        too_large = False

        async def _receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    # Signal end-of-body to the app so it stops reading
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def _send(message: Message) -> None:
            # If the body was oversized, replace whatever the app wants to send
            # with a 413 response.
            if too_large:
                if message["type"] == "http.response.start":
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 413,
                            "headers": [(b"content-type", b"application/json")],
                        }
                    )
                elif message["type"] == "http.response.body":
                    import json

                    body = json.dumps({"detail": "Request body too large"}).encode()
                    await send({"type": "http.response.body", "body": body, "more_body": False})
            else:
                await send(message)

        await self.app(scope, _receive, _send)
