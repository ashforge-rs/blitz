from abc import ABC, abstractmethod
from datetime import datetime  # noqa: TC003 — part of the port's signature


class Clock(ABC):
    """Port: the current time, injected so the rules are testable at any moment."""

    @abstractmethod
    def now(self) -> datetime: ...
