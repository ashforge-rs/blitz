"""Use cases wired to in-memory fakes, a fixed clock and sequential ids."""

import pytest

from todo_app.kernel import Actor
from todo_app.todos.use_cases import CreateTodo
from todo_app.users.use_cases import AuthenticateToken, RegisterUser
from todo_tests.fakes import (
    FixedClock,
    InMemoryTodosUnitOfWorkFactory,
    InMemoryUsersUnitOfWorkFactory,
    SequentialIds,
    TodoTelemetryRecorder,
    UserTelemetryRecorder,
)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def actor() -> Actor:
    return Actor(user_id=None, correlation_id="req-1", client_address="10.0.0.1:5000")


@pytest.fixture
def users_uow() -> InMemoryUsersUnitOfWorkFactory:
    return InMemoryUsersUnitOfWorkFactory()


@pytest.fixture
def user_telemetry() -> UserTelemetryRecorder:
    return UserTelemetryRecorder()


@pytest.fixture
def register(
    users_uow: InMemoryUsersUnitOfWorkFactory,
    user_telemetry: UserTelemetryRecorder,
    clock: FixedClock,
) -> RegisterUser:
    return RegisterUser(users_uow, user_telemetry, clock=clock, ids=SequentialIds("id"))


@pytest.fixture
def authenticate(
    users_uow: InMemoryUsersUnitOfWorkFactory, user_telemetry: UserTelemetryRecorder
) -> AuthenticateToken:
    return AuthenticateToken(users_uow, user_telemetry)


@pytest.fixture
def todos_uow() -> InMemoryTodosUnitOfWorkFactory:
    return InMemoryTodosUnitOfWorkFactory()


@pytest.fixture
def todo_telemetry() -> TodoTelemetryRecorder:
    return TodoTelemetryRecorder()


@pytest.fixture
def create_todo(
    todos_uow: InMemoryTodosUnitOfWorkFactory,
    todo_telemetry: TodoTelemetryRecorder,
    clock: FixedClock,
) -> CreateTodo:
    return CreateTodo(todos_uow, todo_telemetry, clock=clock, ids=SequentialIds("id"))
