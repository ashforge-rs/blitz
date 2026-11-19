"""
Typed accessors for objects stored on ``app.state``.

``app.state`` is an untyped bag, so reading from it directly means string keys
and ``cast()`` — a typo or a wrong type only surfaces at runtime, and mypy
cannot help.  :func:`get_domain` looks domain instances up **by type** and
verifies them with ``isinstance``, so the return type is exact and a mismatch
fails loudly.

Usage in a domain's ``dependencies.py``::

    def _get_order_service(request: Request) -> OrderService:
        return get_domain(request, OrdersDomain).service
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.requests import Request


def get_domain[T](request: Request, kind: type[T]) -> T:
    """
    Return the bootstrapped domain instance of type *kind*.

    Domain instances are indexed by their concrete type during lifespan
    startup (see ``lifespan.py``).

    Raises ``LookupError`` if no domain of that type was bootstrapped — usually
    because the domain module is missing from ``create_app(domains=[...])``.
    """
    registry: dict[type[Any], object] = request.app.state.domains_by_type
    instance = registry.get(kind)
    if instance is None:
        msg = f"domain {kind.__name__!r} is not bootstrapped — add it to create_app(domains=...)"
        raise LookupError(msg)
    if not isinstance(instance, kind):
        msg = f"domain registry entry for {kind.__name__!r} is {type(instance).__name__}"
        raise TypeError(msg)
    return instance
