from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

router = APIRouter(tags=["internal"])

HealthCheckFn = Callable[[], Coroutine[Any, Any, dict[str, Any]]]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LivenessResponse(BaseModel):
    status: str = "ok"


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/live", summary="Liveness probe", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Always returns 200. Use as a Kubernetes liveness probe."""
    return LivenessResponse()


@router.get(
    "/health",
    summary="Readiness probe",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "One or more checks failed"}},
)
async def readiness(request: Request) -> JSONResponse:
    """
    Run all registered health checks and aggregate the result.

    Returns ``200 {"status": "ok"}`` when all checks pass.
    Returns ``503 {"status": "degraded"}`` when any check fails.

    Register checks by passing a list of async callables to ``create_app``::

        async def check_db() -> dict:
            ok = await db.ping()
            return {"name": "database", "healthy": ok}

        app = create_app(health_checks=[check_db])

    Each callable must return a dict with at least ``"name"`` and ``"healthy"`` keys.
    Any extra keys are included in the response body.
    """
    checks: list[HealthCheckFn] = getattr(request.app.state, "health_checks", [])
    results: dict[str, Any] = {}
    failed = False

    for check in checks:
        try:
            result = await check()
            name = result.get("name", check.__name__)
            results[name] = result
            if not result.get("healthy", True):
                failed = True
        except Exception:
            results[getattr(check, "__name__", "unknown")] = {
                "healthy": False,
                "error": "Health check failed",
            }
            failed = True

    return JSONResponse(
        content=HealthResponse(
            status="degraded" if failed else "ok",
            checks=results,
        ).model_dump(),
        status_code=503 if failed else 200,
    )
