import pytest

from errors.exceptions import (
    AppError,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    ServiceUnavailableError,
    UnauthorizedError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("exc_type", "status"),
    [
        (AppError, 500),
        (ConflictError, 409),
        (ValidationError, 422),
        (UnauthorizedError, 401),
        (ForbiddenError, 403),
        (RateLimitedError, 429),
        (ServiceUnavailableError, 503),
        (ExternalServiceError, 502),
    ],
)
def test_status_codes_and_default_messages(exc_type, status):
    exc = exc_type()
    assert exc.status_code == status
    assert exc.message == exc_type.default_message
    http = exc.as_http_exception()
    assert (http.status_code, http.detail) == (status, exc.message)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("Order", 42), "Order '42' not found"),
        (("Order",), "Order not found"),
        ((), "Resource not found"),
    ],
)
def test_not_found_message(args, message):
    assert NotFoundError(*args).message == message


async def test_app_error_handler_returns_status(client, app):
    @app.get("/conflict")
    async def conflict():
        raise ConflictError("email already registered")

    r = await client.get("/conflict")
    assert r.status_code == 409
