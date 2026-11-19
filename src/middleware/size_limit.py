import json
from typing import TYPE_CHECKING

from errors.problem import PROBLEM_JSON, problem, problem_response

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE_BODY = json.dumps(problem(413, "Request body too large")).encode()


def _parse_content_length(raw: bytes) -> int | None:
    """Return the Content-Length value, or ``None`` if it is not a valid non-negative int."""
    if not raw.isdigit():  # rejects "", "-1", "1.5", " 10", "abc"
        return None
    return int(raw)


class RequestSizeLimitMiddleware:
    """
    Reject requests whose body exceeds *max_bytes*.

    - A malformed ``Content-Length`` header → ``400``.
    - A ``Content-Length`` above the limit → ``413`` before the body is read.
    - Chunked-encoded requests without ``Content-Length`` are rejected with
      ``413`` once the accumulated body bytes exceed the limit.
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
        if raw_cl is not None:
            content_length = _parse_content_length(raw_cl)
            if content_length is None:
                response = problem_response(400, "Invalid Content-Length header")
                await response(scope, receive, send)
                return
            if content_length > self.max_bytes:
                response = problem_response(413, "Request body too large")
                await response(scope, receive, send)
                return

        # Slow path: count streamed bytes; raise a flag if limit is exceeded
        received: int = 0
        too_large = False
        body_sent = False

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
            # with a single 413 response (extra body chunks are dropped).
            nonlocal body_sent
            if not too_large:
                await send(message)
                return
            if message["type"] == "http.response.start":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", PROBLEM_JSON.encode()),
                            (b"content-length", str(len(_TOO_LARGE_BODY)).encode()),
                        ],
                    }
                )
            elif message["type"] == "http.response.body" and not body_sent:
                body_sent = True
                await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})

        await self.app(scope, _receive, _send)
