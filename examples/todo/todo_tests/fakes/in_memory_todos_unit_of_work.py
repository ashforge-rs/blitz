from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Self

from todo_app.kernel import AuditTrail, IdempotencyStore
from todo_app.todos.ports import TodoRepository, TodosUnitOfWork, TodosUnitOfWorkFactory

if TYPE_CHECKING:
    from types import TracebackType

    from todo_app.kernel import AuditRecord, IdempotencyRecord
    from todo_app.todos.entities import Todo


@dataclass
class TodosState:
    todos: dict[str, Todo] = field(default_factory=dict)
    audit: list[AuditRecord] = field(default_factory=list)
    idempotency: dict[tuple[str, str], IdempotencyRecord] = field(default_factory=dict)

    def copy(self) -> TodosState:
        return replace(
            self, todos=dict(self.todos), audit=list(self.audit), idempotency=dict(self.idempotency)
        )


class InMemoryTodosUnitOfWorkFactory(TodosUnitOfWorkFactory):
    """``TodosUnitOfWorkFactory`` with real transaction semantics, in memory."""

    def __init__(self) -> None:
        self.state = TodosState()
        self.commits = 0
        self.fail_with: Exception | None = None

    def __call__(self, *, read_only: bool = False) -> InMemoryTodosUnitOfWork:
        return InMemoryTodosUnitOfWork(self, read_only=read_only)


class InMemoryTodosUnitOfWork(TodosUnitOfWork):
    def __init__(self, factory: InMemoryTodosUnitOfWorkFactory, *, read_only: bool) -> None:
        self._factory = factory
        self._read_only = read_only
        self._work = factory.state.copy()

    @property
    def todos(self) -> InMemoryTodoRepository:
        return InMemoryTodoRepository(self._work)

    @property
    def audit(self) -> InMemoryTodosAuditTrail:
        return InMemoryTodosAuditTrail(self._work)

    @property
    def idempotency(self) -> InMemoryTodosIdempotencyStore:
        return InMemoryTodosIdempotencyStore(self._work)

    async def __aenter__(self) -> Self:
        if self._factory.fail_with is not None:
            raise self._factory.fail_with
        self._work = self._factory.state.copy()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None and not self._read_only:
            self._factory.state = self._work
            self._factory.commits += 1


class InMemoryTodoRepository(TodoRepository):
    def __init__(self, state: TodosState) -> None:
        self._s = state

    async def add(self, todo: Todo) -> None:
        self._s.todos[todo.id] = todo

    async def get(self, todo_id: str) -> Todo | None:
        return self._s.todos.get(todo_id)


class InMemoryTodosAuditTrail(AuditTrail):
    def __init__(self, state: TodosState) -> None:
        self._s = state

    async def record(self, entry: AuditRecord) -> None:
        self._s.audit.append(entry)


class InMemoryTodosIdempotencyStore(IdempotencyStore):
    def __init__(self, state: TodosState) -> None:
        self._s = state

    async def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        return self._s.idempotency.get((scope, key))

    async def put(self, record: IdempotencyRecord) -> None:
        self._s.idempotency[(record.scope, record.key)] = record
