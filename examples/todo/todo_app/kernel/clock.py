from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    """Port: the current time.  Injected so use cases are deterministic under test."""

    @abstractmethod
    def now(self) -> datetime: ...


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
