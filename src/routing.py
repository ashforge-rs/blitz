"""
:class:`ResultRouter` — an ``APIRouter`` for handlers that return ``Result``.

Every endpoint registered on it is wrapped so that:

- ``Success(value)`` → ``value`` is serialised as the response;
- ``Failure(DomainError)`` → :class:`errors.domain.DomainFailure` is raised and the
  global handler renders an RFC 9457 problem response;
- ``Failure(exception)`` → the exception is re-raised;
- anything else passes through unchanged.

When the return annotation is ``Result[T, E]`` and no ``response_model`` is
given, ``response_model`` defaults to ``T`` — so ``-> Result[Order, OrderError]``
documents ``Order`` in OpenAPI without repeating it in the decorator.
"""

import inspect
import typing
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import APIRouter
from fastapi.datastructures import Default, DefaultPlaceholder
from returns.result import Failure, Result, Success

from errors.domain import DomainError, DomainFailure


def _unwrap(rv: Any) -> Any:
    match rv:
        case Success(value):
            return value
        case Failure(DomainError() as error):
            raise DomainFailure(error)
        case Failure(BaseException() as exc):
            raise exc
        case Failure(other):
            msg = f"Failure must hold a DomainError or an exception, got {type(other).__name__}"
            raise TypeError(msg)
        case _:
            return rv


def unwrap_result(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap *endpoint* so its ``Result`` return value is unwrapped (see module docs)."""
    if inspect.iscoroutinefunction(endpoint):

        @wraps(endpoint)
        async def _async(*args: Any, **kwargs: Any) -> Any:
            return _unwrap(await endpoint(*args, **kwargs))

        wrapper: Callable[..., Any] = _async
    else:
        # Keep sync endpoints sync so FastAPI still runs them in the threadpool.
        @wraps(endpoint)
        def _sync(*args: Any, **kwargs: Any) -> Any:
            return _unwrap(endpoint(*args, **kwargs))

        wrapper = _sync

    # FastAPI resolves dependencies from the signature, so keep the original
    # parameters.  Drop a ``Result[...]`` return annotation: FastAPI would try to
    # build a response model from it (ResultRouter derives the real one instead).
    signature = inspect.signature(endpoint)
    if _result_args(endpoint) is not None:
        signature = signature.replace(return_annotation=inspect.Signature.empty)
    wrapper.__signature__ = signature  # type: ignore[attr-defined]
    return wrapper


def _result_args(endpoint: Callable[..., Any]) -> tuple[Any, ...] | None:
    """``(T, E)`` for an endpoint annotated ``-> Result[T, E]``, else ``None``."""
    try:
        annotation = inspect.signature(endpoint).return_annotation
    except NameError:  # annotation refers to a TYPE_CHECKING-only name
        return None
    if typing.get_origin(annotation) is Result:
        return typing.get_args(annotation)
    return None


class ResultRouter(APIRouter):
    """``APIRouter`` whose endpoints may return ``Result[T, DomainError]``."""

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        # Only fill in a model the caller left at FastAPI's default — an explicit
        # ``response_model=None`` still means "no model".
        response_model = kwargs.get("response_model", Default(None))
        args = _result_args(endpoint)
        if isinstance(response_model, DefaultPlaceholder) and args is not None:
            value_type = args[0]
            kwargs["response_model"] = None if value_type in (None, type(None)) else value_type
        super().add_api_route(path, unwrap_result(endpoint), **kwargs)
