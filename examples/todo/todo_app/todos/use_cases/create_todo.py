from dataclasses import dataclass
from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from todo_app.kernel import (
    AuditEntries,
    IdempotencyConflictError,
    IdempotencyRecord,
    StorageUnavailableError,
    fingerprint,
    retry_once_on_key_race,
)
from todo_app.todos.entities import Todo

from .errors import TodoError, TodoErrorCode, todo_error

if TYPE_CHECKING:
    from todo_app.kernel import Actor, Clock, IdGenerator
    from todo_app.todos.entities import Title
    from todo_app.todos.ports import TodosUnitOfWork, TodosUnitOfWorkFactory, TodoTelemetry

OPERATION = "todos.create"


@dataclass(frozen=True, slots=True)
class TodoCreated:
    todo: Todo
    #: True when an Idempotency-Key retry returned the todo created earlier.
    replayed: bool = False


class CreateTodo:
    """Create a todo for its owner.

    The todo, its audit entry and its idempotency record are one unit of work.
    """

    def __init__(
        self,
        uow: TodosUnitOfWorkFactory,
        telemetry: TodoTelemetry,
        *,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow
        self._telemetry = telemetry
        self._clock = clock
        self._ids = ids
        self._audit = AuditEntries(OPERATION, clock=clock, ids=ids)

    async def execute(
        self, owner_id: str, title: Title, actor: Actor, *, idempotency_key: str | None = None
    ) -> Result[TodoCreated, TodoError]:
        async def attempt() -> TodoCreated:
            async with self._uow() as uow:
                return await self._create(uow, owner_id, title, actor, idempotency_key)

        try:
            created = await retry_once_on_key_race(attempt)
        except IdempotencyConflictError:
            return await self._reject(TodoErrorCode.IDEMPOTENCY_KEY_REUSED, actor)
        except StorageUnavailableError as exc:
            await self._telemetry.storage_failed(OPERATION, exc, actor)
            return Failure(todo_error(TodoErrorCode.STORAGE_ERROR))

        await self._telemetry.created(created.todo, actor, replayed=created.replayed)
        return Success(created)

    async def _create(
        self,
        uow: TodosUnitOfWork,
        owner_id: str,
        title: Title,
        actor: Actor,
        idempotency_key: str | None,
    ) -> TodoCreated:
        now = self._clock.now()
        # Keys are scoped per owner: one user's key can never replay another user's todo.
        scope = f"{OPERATION}:{owner_id}"
        request = fingerprint(OPERATION, title.value)
        if idempotency_key is not None:
            previous = await uow.idempotency.get(scope, idempotency_key)
            if previous is not None and previous.is_live(now):
                if previous.request_fingerprint != request:
                    raise IdempotencyConflictError
                todo = await uow.todos.get(previous.resource_id)
                if todo is None:
                    raise IdempotencyConflictError
                return TodoCreated(todo=todo, replayed=True)

        todo = Todo(
            id=self._ids.new_id(), owner_id=owner_id, title=title, done=False, created_at=now
        )
        await uow.todos.add(todo)
        await uow.audit.record(self._audit.success(actor, resource_id=todo.id))
        if idempotency_key is not None:
            await uow.idempotency.add(
                IdempotencyRecord(
                    scope=scope,
                    key=idempotency_key,
                    request_fingerprint=request,
                    resource_id=todo.id,
                    created_at=now,
                )
            )
        return TodoCreated(todo=todo)

    async def _reject(self, reason: TodoErrorCode, actor: Actor) -> Result[TodoCreated, TodoError]:
        """Audit a refused creation in its own unit of work (the attempt rolled back)."""
        try:
            async with self._uow() as uow:
                await uow.audit.record(self._audit.failure(actor, details={"reason": reason}))
        except StorageUnavailableError as exc:
            await self._telemetry.storage_failed(OPERATION, exc, actor)
            return Failure(todo_error(TodoErrorCode.STORAGE_ERROR))
        await self._telemetry.rejected(reason, actor)
        return Failure(todo_error(reason))
