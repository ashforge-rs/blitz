import uuid
from datetime import UTC, datetime

from consent_app.ports import Clock, IdGenerator


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class Uuid7Ids(IdGenerator):
    """Time-ordered UUIDv7 strings: ledger inserts stay index-friendly."""

    def new_id(self) -> str:
        return str(uuid.uuid7())
