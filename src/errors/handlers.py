from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException

from errors.exceptions import AppError


def register_error_handlers(app: FastAPI, *, is_production: bool = True) -> None:
    """
    Register global exception handlers on *app*.

    - ``RequestValidationError`` → 422 with field-level detail.
    - ``HTTPException`` → passthrough with original status code.
    - Any other ``Exception`` → 500.

      * **Production**: body is sanitised to ``{"detail": "Internal server error"}``
        to prevent stack traces or internal state from leaking to clients.
      * **Development**: body also includes ``type`` and ``message`` for easier debugging.

      The full traceback is always logged via Loguru regardless of environment.
    """

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.opt(exception=True).error(
            "Unhandled exception",
            method=request.method,
            path=request.url.path,
        )
        if is_production:
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": type(exc).__name__,
                "message": str(exc),
            },
        )
