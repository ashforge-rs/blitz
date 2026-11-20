from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException

from errors.domain import DomainFailure
from errors.exceptions import AppError
from errors.problem import problem_response


def register_error_handlers(app: FastAPI, *, is_production: bool = True) -> None:
    """
    Register global exception handlers on *app*.

    Every handler returns an RFC 9457 Problem Details body
    (``application/problem+json``, see :mod:`errors.problem`):

    - ``RequestValidationError`` → 422 with field-level ``errors``.
    - ``AppError`` → its ``status_code`` and ``message``.
    - ``DomainFailure`` (a route returned ``Failure(DomainError)``) → the error's
      ``status``, ``detail`` and ``code``; 5xx messages are logged, not sent.
    - ``HTTPException`` → passthrough with original status code and headers.
    - Any other ``Exception`` → 500.

      * **Production**: ``detail`` is the generic ``"Internal server error"`` —
        no stack traces or internal state leak to clients.
      * **Development**: adds ``exception`` (class name) and
        ``exception_message`` extension members for easier debugging.

      The full traceback is always logged via Loguru regardless of environment.
    """

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            422, "Request validation failed", request=request, errors=exc.errors()
        )

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(exc.status_code, exc.message, request=request)

    @app.exception_handler(DomainFailure)
    async def _domain_failure(request: Request, exc: DomainFailure) -> JSONResponse:
        error = exc.error
        if error.status >= 500:
            logger.error(
                "Domain failure",
                code=str(error.code),
                message=error.message,
                method=request.method,
                path=request.url.path,
            )
        return problem_response(error.status, error.detail, request=request, code=error.code)

    @app.exception_handler(HTTPException)
    async def _http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        # A structured detail (dict/list) is kept as the `errors` extension.
        structured = not isinstance(exc.detail, str)
        return problem_response(
            exc.status_code,
            None if structured else exc.detail,
            request=request,
            headers=exc.headers,
            errors=exc.detail if structured else None,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.opt(exception=True).error(
            "Unhandled exception",
            method=request.method,
            path=request.url.path,
        )
        if is_production:
            return problem_response(500, "Internal server error", request=request)
        return problem_response(
            500,
            "Internal server error",
            request=request,
            exception=type(exc).__name__,
            exception_message=str(exc),
        )
