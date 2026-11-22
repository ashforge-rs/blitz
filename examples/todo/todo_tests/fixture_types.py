"""Types of the fixtures in ``conftest.py``, for annotating test parameters."""

from collections.abc import Awaitable, Callable
from typing import Any

#: ``await register_user(email=..., name=...)`` → the 201 registration body.
type RegisterUser = Callable[..., Awaitable[dict[str, Any]]]
#: ``metric(name, **labels)`` → the sample's current value (0 if unset).
type Metric = Callable[..., float]
#: ``await flush_audit()`` → every pending outbox entry delivered to ``audit_log``.
type FlushAudit = Callable[[], Awaitable[None]]
