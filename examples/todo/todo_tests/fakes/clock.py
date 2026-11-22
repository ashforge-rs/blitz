from datetime import UTC, datetime, timedelta

from todo_app.kernel import Clock

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class FixedClock(Clock):
    """Starts at EPOCH and only moves when told to."""

    def __init__(self, start: datetime = EPOCH) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
