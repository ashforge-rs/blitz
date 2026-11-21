import pytest

from todo_app.kernel import Actor, AuditOutcome, StorageUnavailableError
from todo_app.todos.entities import Title, Todo
from todo_app.todos.use_cases import CreateTodo, TodoErrorCode
from todo_tests.fakes import EPOCH, InMemoryTodosUnitOfWorkFactory, TodoTelemetryRecorder

MILK = Title("Buy milk")
KEY = "key-0001"


@pytest.fixture
def ada() -> Actor:
    return Actor(user_id="user-ada", correlation_id="req-1")


async def test_todo_and_audit_entry_commit_together(
    create_todo: CreateTodo, todos_uow: InMemoryTodosUnitOfWorkFactory, ada: Actor
) -> None:
    created = (await create_todo.execute("user-ada", MILK, ada)).unwrap()

    expected = Todo(id="id-1", owner_id="user-ada", title=MILK, done=False, created_at=EPOCH)
    assert created.todo == expected
    assert created.replayed is False
    assert todos_uow.commits == 1
    assert todos_uow.state.todos == {"id-1": expected}
    [entry] = todos_uow.state.audit
    assert (entry.operation, entry.outcome, entry.resource_id) == (
        "todos.create",
        AuditOutcome.SUCCESS,
        "id-1",
    )
    assert entry.actor.user_id == "user-ada"


async def test_retry_with_same_key_returns_the_original_todo(
    create_todo: CreateTodo,
    todos_uow: InMemoryTodosUnitOfWorkFactory,
    todo_telemetry: TodoTelemetryRecorder,
    ada: Actor,
) -> None:
    first = (await create_todo.execute("user-ada", MILK, ada, idempotency_key=KEY)).unwrap()

    retry = (await create_todo.execute("user-ada", MILK, ada, idempotency_key=KEY)).unwrap()

    assert retry.replayed is True
    assert retry.todo == first.todo
    assert len(todos_uow.state.todos) == 1
    assert len(todos_uow.state.audit) == 1  # a replay changes nothing, so it audits nothing
    assert [replayed for _, replayed in todo_telemetry.creations] == [False, True]


async def test_keys_are_scoped_per_owner(
    create_todo: CreateTodo, todos_uow: InMemoryTodosUnitOfWorkFactory, ada: Actor
) -> None:
    bob = Actor(user_id="user-bob", correlation_id="req-2")
    await create_todo.execute("user-ada", MILK, ada, idempotency_key=KEY)

    bobs = (await create_todo.execute("user-bob", MILK, bob, idempotency_key=KEY)).unwrap()

    assert bobs.replayed is False
    assert bobs.todo.owner_id == "user-bob"
    assert len(todos_uow.state.todos) == 2


async def test_key_reused_for_a_different_title_is_refused(
    create_todo: CreateTodo, todos_uow: InMemoryTodosUnitOfWorkFactory, ada: Actor
) -> None:
    await create_todo.execute("user-ada", MILK, ada, idempotency_key=KEY)

    result = await create_todo.execute("user-ada", Title("Walk dog"), ada, idempotency_key=KEY)

    assert result.failure().code is TodoErrorCode.IDEMPOTENCY_KEY_REUSED
    assert len(todos_uow.state.todos) == 1
    assert todos_uow.state.audit[-1].outcome is AuditOutcome.FAILURE


async def test_storage_outage_is_a_safe_failure(
    create_todo: CreateTodo,
    todos_uow: InMemoryTodosUnitOfWorkFactory,
    todo_telemetry: TodoTelemetryRecorder,
    ada: Actor,
) -> None:
    outage = StorageUnavailableError("disk I/O error")
    todos_uow.fail_with = outage

    result = await create_todo.execute("user-ada", MILK, ada)

    assert result.failure().code is TodoErrorCode.STORAGE_ERROR
    assert "disk" not in result.failure().message
    assert todo_telemetry.storage_failures == [("todos.create", outage)]


async def test_a_bug_is_not_disguised_as_a_storage_error(
    create_todo: CreateTodo, todos_uow: InMemoryTodosUnitOfWorkFactory, ada: Actor
) -> None:
    todos_uow.fail_with = KeyError("bug")

    with pytest.raises(KeyError):
        await create_todo.execute("user-ada", MILK, ada)
