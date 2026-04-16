from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram


def _get_or_create(collector_type: type, name: str, documentation: str, **kwargs: Any) -> Any:
    """Return an existing collector or create and register a new one."""
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing
    return collector_type(name, documentation, **kwargs)


def counter(
    name: str,
    documentation: str,
    labelnames: list[str] | None = None,
) -> Counter:
    """Create (or retrieve) a ``Counter`` in the default Prometheus registry."""
    try:
        return Counter(name, documentation, labelnames or [], registry=REGISTRY)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


def histogram(
    name: str,
    documentation: str,
    labelnames: list[str] | None = None,
    buckets: tuple[float, ...] | None = None,
) -> Histogram:
    """Create (or retrieve) a ``Histogram`` in the default Prometheus registry."""
    kwargs: dict[str, Any] = {"registry": REGISTRY, "labelnames": labelnames or []}
    if buckets is not None:
        kwargs["buckets"] = buckets
    try:
        return Histogram(name, documentation, **kwargs)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]
