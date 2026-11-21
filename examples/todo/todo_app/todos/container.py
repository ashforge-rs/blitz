"""Composition root of the todos context, independent of any delivery mechanism."""

from typing import TYPE_CHECKING

from todo_app.kernel import SystemClock, Uuid7Ids
from todo_app.persistence import open_context_runtime

from .adapters.observed_todo_telemetry import ObservedTodoTelemetry
from .adapters.sql_migrations import MIGRATIONS
from .adapters.sql_tables import audit_outbox
from .adapters.sql_todos_unit_of_work import SqlTodosUnitOfWorkFactory
from .use_cases import CreateTodo

if TYPE_CHECKING:
    from audit.backend import AuditBackend, AuditIntegrity

    from todo_app.persistence import ContextRuntime, OutboxRelay
    from todo_app.settings import TodoSettings


class TodosDomain:
    """The todos context's use cases and the runtime (database, audit relay) behind them."""

    def __init__(self, *, create: CreateTodo, runtime: ContextRuntime) -> None:
        self.create = create
        self._runtime = runtime

    @property
    def relay(self) -> OutboxRelay:
        return self._runtime.relay

    async def health(self, *, max_outbox_age_s: float) -> dict[str, object]:
        return await self._runtime.health(max_outbox_age_s=max_outbox_age_s)

    async def aclose(self) -> None:
        await self._runtime.aclose()


async def build_todos(
    settings: TodoSettings,
    *,
    audit_backend: AuditBackend,
    audit_integrity: AuditIntegrity,
    poll_outbox: bool = True,
) -> TodosDomain:
    runtime = await open_context_runtime(
        "todos",
        settings,
        migrations=MIGRATIONS,
        outbox=audit_outbox,
        audit_backend=audit_backend,
        audit_integrity=audit_integrity,
        poll_outbox=poll_outbox,
    )
    create = CreateTodo(
        SqlTodosUnitOfWorkFactory(runtime.db),
        ObservedTodoTelemetry(),
        clock=SystemClock(),
        ids=Uuid7Ids(),
    )
    return TodosDomain(create=create, runtime=runtime)
