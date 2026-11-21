import pytest

from todo_app.kernel import IDEMPOTENCY_TTL, Actor, AuditOutcome, StorageUnavailableError
from todo_app.users.entities import DisplayName, EmailAddress, hash_token
from todo_app.users.use_cases import RegisterUser, UserErrorCode
from todo_tests.fakes import (
    EPOCH,
    FixedClock,
    InMemoryUsersUnitOfWorkFactory,
    UserTelemetryRecorder,
)

ADA = EmailAddress("ada@example.com")
NAME = DisplayName("Ada")
KEY = "key-0001"


async def test_user_token_and_audit_entry_commit_together(
    register: RegisterUser, users_uow: InMemoryUsersUnitOfWorkFactory, actor: Actor
) -> None:
    registration = (await register.execute(ADA, NAME, actor)).unwrap()

    state = users_uow.state
    assert users_uow.commits == 1
    assert state.users == {registration.user.id: registration.user}
    assert state.tokens == {hash_token(registration.api_token): registration.user.id}
    [entry] = state.audit
    assert (entry.operation, entry.outcome) == ("users.register", AuditOutcome.SUCCESS)
    assert entry.resource_id == registration.user.id
    assert entry.actor == actor
    assert entry.occurred_at == EPOCH


async def test_only_the_token_hash_is_stored(
    register: RegisterUser, users_uow: InMemoryUsersUnitOfWorkFactory, actor: Actor
) -> None:
    token = (await register.execute(ADA, NAME, actor)).unwrap().api_token

    assert token.startswith("tdo_")
    assert token not in repr(users_uow.state)


async def test_duplicate_email_changes_nothing_but_is_audited(
    register: RegisterUser,
    users_uow: InMemoryUsersUnitOfWorkFactory,
    user_telemetry: UserTelemetryRecorder,
    actor: Actor,
) -> None:
    await register.execute(ADA, NAME, actor)

    result = await register.execute(EmailAddress("ADA@example.com"), DisplayName("Eve"), actor)

    assert result.failure().code is UserErrorCode.EMAIL_TAKEN
    assert len(users_uow.state.users) == 1
    assert len(users_uow.state.tokens) == 1  # the attempt's token rolled back with it
    rejected = users_uow.state.audit[-1]
    assert rejected.outcome is AuditOutcome.FAILURE
    assert rejected.details == {"reason": "email_taken"}
    assert user_telemetry.rejections == [UserErrorCode.EMAIL_TAKEN]


async def test_retry_with_same_key_returns_the_user_with_a_fresh_token(
    register: RegisterUser, users_uow: InMemoryUsersUnitOfWorkFactory, actor: Actor
) -> None:
    first = (await register.execute(ADA, NAME, actor, idempotency_key=KEY)).unwrap()

    retry = (await register.execute(ADA, NAME, actor, idempotency_key=KEY)).unwrap()

    assert retry.replayed is True
    assert retry.user == first.user
    assert retry.api_token != first.api_token
    # Exactly one valid token from this registration: the undelivered one is revoked.
    assert users_uow.state.tokens == {hash_token(retry.api_token): first.user.id}
    assert users_uow.state.audit[-1].details == {"replayed": "true"}


async def test_key_reused_for_different_content_is_refused(
    register: RegisterUser, users_uow: InMemoryUsersUnitOfWorkFactory, actor: Actor
) -> None:
    await register.execute(ADA, NAME, actor, idempotency_key=KEY)

    result = await register.execute(
        EmailAddress("bob@example.com"), DisplayName("Bob"), actor, idempotency_key=KEY
    )

    assert result.failure().code is UserErrorCode.IDEMPOTENCY_KEY_REUSED
    assert len(users_uow.state.users) == 1
    assert users_uow.state.audit[-1].details == {"reason": "idempotency_key_reused"}


async def test_expired_key_is_not_replayed(
    register: RegisterUser, clock: FixedClock, actor: Actor
) -> None:
    await register.execute(ADA, NAME, actor, idempotency_key=KEY)
    clock.advance(IDEMPOTENCY_TTL.total_seconds())

    result = await register.execute(ADA, NAME, actor, idempotency_key=KEY)

    assert result.failure().code is UserErrorCode.EMAIL_TAKEN  # a new attempt, not a replay


async def test_storage_outage_is_a_safe_failure(
    register: RegisterUser,
    users_uow: InMemoryUsersUnitOfWorkFactory,
    user_telemetry: UserTelemetryRecorder,
    actor: Actor,
) -> None:
    outage = StorageUnavailableError("database is locked")
    users_uow.fail_with = outage

    result = await register.execute(ADA, NAME, actor)

    error = result.failure()
    assert error.code is UserErrorCode.STORAGE_ERROR
    assert "locked" not in error.message  # raw driver text never reaches callers or audit
    assert user_telemetry.storage_failures == [("users.register", outage)]


async def test_a_bug_is_not_disguised_as_a_storage_error(
    register: RegisterUser, users_uow: InMemoryUsersUnitOfWorkFactory, actor: Actor
) -> None:
    users_uow.fail_with = TypeError("bug in an adapter")

    with pytest.raises(TypeError, match="bug in an adapter"):
        await register.execute(ADA, NAME, actor)
