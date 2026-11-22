"""
RFC 9457 *Problem Details for HTTP APIs* — the single error body format.

Every error response produced by the framework (exception handlers and
middleware) uses ``application/problem+json``::

    {
      "type": "about:blank",
      "title": "Not Found",
      "status": 404,
      "detail": "Order '42' not found",
      "instance": "/v1/orders/42",
      "request_id": "0f8fad5b..."
    }

``type`` defaults to ``about:blank`` (RFC 9457 §4.2.1), in which case ``title``
is the HTTP reason phrase.  Pass a URI ``type`` for machine-readable,
documented problem categories.  Extra keyword arguments become extension
members (e.g. ``errors`` for validation failures, ``request_id``).

``detail`` is always present so clients that read ``body["detail"]`` keep
working.
"""

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.requests import Request

PROBLEM_JSON = "application/problem+json"


def _reason(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem(
    status: int,
    detail: str | None = None,
    *,
    title: str | None = None,
    type_: str = "about:blank",
    instance: str | None = None,
    **extensions: Any,
) -> dict[str, Any]:
    """Build a Problem Details body (a plain dict)."""
    body: dict[str, Any] = {
        "type": type_,
        "title": title or _reason(status),
        "status": status,
        "detail": detail if detail is not None else _reason(status),
    }
    if instance is not None:
        body["instance"] = instance
    body.update({k: v for k, v in extensions.items() if v is not None})
    return body


def problem_response(
    status: int,
    detail: str | None = None,
    *,
    request: Request | None = None,
    headers: Mapping[str, str] | None = None,
    title: str | None = None,
    type_: str = "about:blank",
    **extensions: Any,
) -> JSONResponse:
    """
    Return an ``application/problem+json`` response.

    When *request* is given, ``instance`` is set to the request path and
    ``request_id`` to the current request's ID (if the context middleware ran).
    """
    instance: str | None = None
    if request is not None:
        instance = request.url.path
        ctx = getattr(request.state, "ctx", None)
        extensions.setdefault("request_id", getattr(ctx, "request_id", None))
    body = problem(status, detail, title=title, type_=type_, instance=instance, **extensions)
    return JSONResponse(
        jsonable_encoder(body),
        status_code=status,
        headers=dict(headers) if headers else None,
        media_type=PROBLEM_JSON,
    )
