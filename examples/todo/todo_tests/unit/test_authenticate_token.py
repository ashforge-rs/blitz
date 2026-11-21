import pytest
from returns.result import Success

from todo_app.kernel import Actor, StorageUnavailableError
from todo_app.users.entities import DisplayName, EmailAddress
from todo_app.users.use_cases import AuthenticateToken, RegisterUser, UserErrorCode
from todo_tests.fakes import InMemoryUsersUnitOfWorkFactory, UserTelemetryRecorder


async def _register(register: RegisterUser, actor: Actor, key: str | None = None) -> str:
    registration = await register.execute(
        EmailAddress("ada@example.com"), DisplayName("Ada"), actor, idempotency_key=key
    )
    return registration.unwrap().api_token


async def test_resolves_a_registered_token(
    register: RegisterUser, authenticate: AuthenticateToken, actor: Actor
) -> None:
    token = await _register(register, actor)

    result = await authenticate.execute(token, actor)

    assert isinstance(result, Success)
    assert result.unwrap().email == EmailAddress("ada@example.com")


async def test_reads_do_not_commit(
    register: RegisterUser,
    authenticate: AuthenticateToken,
    users_uow: InMemoryUsersUnitOfWorkFactory,
    actor: Actor,
) -> None:
    token = await _register(register, actor)
    commits = users_uow.commits

    await authenticate.execute(token, actor)

    assert users_uow.commits == commits


async def test_token_revoked_by_a_replay_no_longer_works(
    register: RegisterUser, authenticate: AuthenticateToken, actor: Actor
) -> None:
    undelivered = await _register(register, actor, key="key-0001")
    delivered = await _register(register, actor, key="key-0001")

    assert (await authenticate.execute(undelivered, actor)).failure().code is (
        UserErrorCode.INVALID_TOKEN
    )
    assert isinstance(await authenticate.execute(delivered, actor), Success)


@pytest.mark.parametrize("token", ["tdo_unknown", "not-a-token", ""])
async def test_rejects_unknown_or_malformed_tokens(
    authenticate: AuthenticateToken, actor: Actor, token: str
) -> None:
    result = await authenticate.execute(token, actor)

    assert result.failure().code is UserErrorCode.INVALID_TOKEN


async def test_malformed_token_never_opens_a_unit_of_work(
    authenticate: AuthenticateToken, users_uow: InMemoryUsersUnitOfWorkFactory, actor: Actor
) -> None:
    users_uow.fail_with = AssertionError("storage must not be touched")

    result = await authenticate.execute("Basic abc", actor)

    assert result.failure().code is UserErrorCode.INVALID_TOKEN


async def test_storage_outage_is_reported_not_mistaken_for_a_bad_token(
    authenticate: AuthenticateToken,
    users_uow: InMemoryUsersUnitOfWorkFactory,
    user_telemetry: UserTelemetryRecorder,
    actor: Actor,
) -> None:
    outage = StorageUnavailableError("disk I/O error")
    users_uow.fail_with = outage

    result = await authenticate.execute("tdo_whatever", actor)

    assert result.failure().code is UserErrorCode.STORAGE_ERROR
    assert user_telemetry.storage_failures == [("users.authenticate", outage)]
