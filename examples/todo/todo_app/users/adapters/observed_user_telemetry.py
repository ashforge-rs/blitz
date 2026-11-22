"""``UserTelemetry``: Prometheus counters and logs.

Emails and tokens are personal data and secrets, so they are never logged;
entries carry the user id only.
"""

from typing import TYPE_CHECKING

from loguru import logger
from metrics import counter

from todo_app.users.ports import UserTelemetry

if TYPE_CHECKING:
    from todo_app.kernel import Actor, StorageUnavailableError
    from todo_app.users.entities import User
    from todo_app.users.use_cases import UserErrorCode

#: result: success | replayed | email_taken | idempotency_key_reused | error
USERS_REGISTERED = counter(
    "todoapp_users_registered_total",
    "User registrations, by outcome",
    ["result"],
)
#: operation: users.register | users.authenticate
USERS_STORAGE_FAILURES = counter(
    "todoapp_users_storage_failures_total",
    "Users operations that failed because storage was unavailable",
    ["operation"],
)


class ObservedUserTelemetry(UserTelemetry):
    """Never raises (the port's contract): a failure here is logged and swallowed."""

    async def registered(self, user: User, actor: Actor, *, replayed: bool) -> None:
        try:
            USERS_REGISTERED.labels(result="replayed" if replayed else "success").inc()
            logger.info(
                "user.registered",
                user_id=user.id,
                replayed=replayed,
                request_id=actor.correlation_id,
            )
        except Exception:  # noqa: BLE001 — telemetry must not change a committed result
            logger.exception("telemetry.failed")

    async def registration_rejected(self, reason: UserErrorCode, actor: Actor) -> None:
        try:
            USERS_REGISTERED.labels(result=reason.value).inc()
            logger.info(
                "user.register.rejected", reason=reason.value, request_id=actor.correlation_id
            )
        except Exception:  # noqa: BLE001 — telemetry must not change the result
            logger.exception("telemetry.failed")

    async def storage_failed(
        self, operation: str, error: StorageUnavailableError, actor: Actor
    ) -> None:
        try:
            USERS_STORAGE_FAILURES.labels(operation=operation).inc()
            if operation == "users.register":
                USERS_REGISTERED.labels(result="error").inc()
            logger.error(
                "user.storage_unavailable",
                operation=operation,
                error=str(error),
                request_id=actor.correlation_id,
            )
        except Exception:  # noqa: BLE001 — telemetry must not change the result
            logger.exception("telemetry.failed")
