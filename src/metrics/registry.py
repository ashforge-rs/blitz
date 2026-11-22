from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram


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
