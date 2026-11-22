from datetime import UTC, datetime, timedelta

from consent_app.ports import Clock

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class FixedClock(Clock):
    def __init__(self, start: datetime = EPOCH) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)
