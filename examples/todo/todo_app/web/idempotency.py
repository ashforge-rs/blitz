from typing import Annotated

from fastapi import Header, Response

from todo_app.kernel import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    IDEMPOTENCY_KEY_MIN_LENGTH,
    IDEMPOTENCY_KEY_PATTERN,
)

#: Optional ``Idempotency-Key`` request header: a client-chosen random value (a UUID) that
#: makes a retried POST return the original result instead of creating a second one.
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=IDEMPOTENCY_KEY_MIN_LENGTH,
        max_length=IDEMPOTENCY_KEY_MAX_LENGTH,
        pattern=IDEMPOTENCY_KEY_PATTERN,
        description="Random per-request value; retries with the same value are not repeated.",
    ),
]


def mark_replayed(response: Response) -> None:
    response.headers["Idempotent-Replayed"] = "true"
