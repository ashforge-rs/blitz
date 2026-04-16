from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.requests import Request

router = APIRouter(tags=["internal"])


@router.get("/metrics", response_class=PlainTextResponse, summary="Prometheus metrics")
async def metrics(request: Request) -> PlainTextResponse:
    """
    Expose Prometheus metrics in the standard text exposition format.

    When ``METRICS_REQUIRE_AUTH=true``, the registered ``AuthProvider.authenticate()``
    must succeed (return a non-None principal) for the endpoint to be accessible.
    """
    if getattr(request.app.state, "metrics_require_auth", False):
        auth_provider = getattr(request.app.state, "auth_provider", None)
        if auth_provider is None:
            # Auth is required but no provider is registered — deny by default
            # rather than silently exposing metrics.
            raise HTTPException(
                status_code=503, detail="Metrics auth required but no auth provider is configured"
            )
        principal = await auth_provider.authenticate(request)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
