"""``TodoTelemetry``: Prometheus counters and logs."""

from typing import TYPE_CHECKING

from loguru import logger
from metrics import counter

from todo_app.todos.ports import TodoTelemetry

if TYPE_CHECKING:
    from todo_app.kernel import Actor, StorageUnavailableError
    from todo_app.todos.entities import Todo
    from todo_app.todos.use_cases import TodoErrorCode

#: result: success | replayed | idempotency_key_reused | error
TODOS_CREATED = counter(
    "todoapp_todos_created_total",
    "Todo creations, by outcome",
    ["result"],
)


class ObservedTodoTelemetry(TodoTelemetry):
    """Never raises (the port's contract): a failure here is logged and swallowed."""

    async def created(self, todo: Todo, actor: Actor, *, replayed: bool) -> None:
        try:
            TODOS_CREATED.labels(result="replayed" if replayed else "success").inc()
            logger.info(
                "todo.created", todo_id=todo.id, replayed=replayed, request_id=actor.correlation_id
            )
        except Exception:  # noqa: BLE001 — telemetry must not change a committed result
            logger.exception("telemetry.failed")

    async def rejected(self, reason: TodoErrorCode, actor: Actor) -> None:
        try:
            TODOS_CREATED.labels(result=reason.value).inc()
            logger.info(
                "todo.create.rejected", reason=reason.value, request_id=actor.correlation_id
            )
        except Exception:  # noqa: BLE001 — telemetry must not change the result
            logger.exception("telemetry.failed")

    async def storage_failed(
        self, operation: str, error: StorageUnavailableError, actor: Actor
    ) -> None:
        try:
            TODOS_CREATED.labels(result="error").inc()
            logger.error(
                "todo.storage_unavailable",
                operation=operation,
                error=str(error),
                request_id=actor.correlation_id,
            )
        except Exception:  # noqa: BLE001 — telemetry must not change the result
            logger.exception("telemetry.failed")
