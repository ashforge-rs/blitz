from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from todo_app.kernel import (
    AuditOutcome,
    AuditRecord,
    IdempotencyConflictError,
    IdempotencyKeyTakenError,
    IdempotencyRecord,
    StorageUnavailableError,
    fingerprint,
)
from todo_app.users.entities import User, generate_token, hash_token
from todo_app.users.ports import EmailTakenError

from .errors import UserError, UserErrorCode, user_error

if TYPE_CHECKING:
    from datetime import datetime

    from todo_app.kernel import Actor, Clock, IdGenerator
    from todo_app.users.entities import DisplayName, EmailAddress
    from todo_app.users.ports import UsersUnitOfWork, UsersUnitOfWorkFactory, UserTelemetry

OPERATION = "users.register"


@dataclass(frozen=True, slots=True)
class Registration:
    user: User
    #: Shown to the caller once; only its hash is stored.
    api_token: str
    #: True when an Idempotency-Key retry returned an earlier registration.
    replayed: bool = False


class RegisterUser:
    """Register a user and issue their first API token.

    The user, the token, the audit entry and the idempotency record are one
    unit of work: all of them are stored, or none.
    """

    def __init__(
        self,
        uow: UsersUnitOfWorkFactory,
        telemetry: UserTelemetry,
        *,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow
        self._telemetry = telemetry
        self._clock = clock
        self._ids = ids

    async def execute(
        self,
        email: EmailAddress,
        name: DisplayName,
        actor: Actor,
        *,
        idempotency_key: str | None = None,
    ) -> Result[Registration, UserError]:
        try:
            registration = await self._attempt(email, name, actor, idempotency_key)
        except EmailTakenError:
            return await self._reject(UserErrorCode.EMAIL_TAKEN, actor)
        except IdempotencyConflictError:
            return await self._reject(UserErrorCode.IDEMPOTENCY_KEY_REUSED, actor)
        except StorageUnavailableError as exc:
            await self._telemetry.storage_failed(OPERATION, exc, actor)
            return Failure(user_error(UserErrorCode.STORAGE_ERROR))

        await self._telemetry.registered(registration.user, actor, replayed=registration.replayed)
        return Success(registration)

    async def _attempt(
        self, email: EmailAddress, name: DisplayName, actor: Actor, idempotency_key: str | None
    ) -> Registration:
        try:
            async with self._uow() as uow:
                return await self._register(uow, email, name, actor, idempotency_key)
        except IdempotencyKeyTakenError:
            # A concurrent request with the same key committed first.  Ours rolled
            # back; run again and replay its result.
            async with self._uow() as uow:
                return await self._register(uow, email, name, actor, idempotency_key)

    async def _register(
        self,
        uow: UsersUnitOfWork,
        email: EmailAddress,
        name: DisplayName,
        actor: Actor,
        idempotency_key: str | None,
    ) -> Registration:
        now = self._clock.now()
        request = fingerprint(OPERATION, email.value, name.value)
        if idempotency_key is not None:
            previous = await uow.idempotency.get(OPERATION, idempotency_key)
            if previous is not None and previous.is_live(now):
                if previous.request_fingerprint != request:
                    raise IdempotencyConflictError
                return await self._reissue(uow, previous, actor, now)

        user = User(id=self._ids.new_id(), email=email, name=name, created_at=now)
        token = generate_token()
        # Uniqueness is the repository's constraint, not a check-then-insert
        # here, so two concurrent registrations can't both win.
        await uow.users.add(user)
        await uow.api_tokens.add(hash_token(token), user.id, now)
        await uow.audit.record(self._audit(AuditOutcome.SUCCESS, actor, now, resource_id=user.id))
        if idempotency_key is not None:
            await uow.idempotency.add(
                IdempotencyRecord(
                    scope=OPERATION,
                    key=idempotency_key,
                    request_fingerprint=request,
                    resource_id=user.id,
                    created_at=now,
                    secret_ref=hash_token(token),
                )
            )
        return Registration(user=user, api_token=token)

    async def _reissue(
        self, uow: UsersUnitOfWork, previous: IdempotencyRecord, actor: Actor, now: datetime
    ) -> Registration:
        """A retried registration: same user, fresh token, the undelivered one revoked.

        The original token's plaintext was never stored, so it can't be returned
        again; rotating keeps "only hashes at rest" true and leaves exactly one
        token from this registration valid.
        """
        user = await uow.users.get(previous.resource_id)
        if user is None:
            raise IdempotencyConflictError
        token = generate_token()
        if previous.secret_ref is not None:
            await uow.api_tokens.revoke(previous.secret_ref)
        await uow.api_tokens.add(hash_token(token), user.id, now)
        await uow.idempotency.replace(replace(previous, secret_ref=hash_token(token)))
        await uow.audit.record(
            self._audit(
                AuditOutcome.SUCCESS, actor, now, resource_id=user.id, details={"replayed": "true"}
            )
        )
        return Registration(user=user, api_token=token, replayed=True)

    async def _reject(self, reason: UserErrorCode, actor: Actor) -> Result[Registration, UserError]:
        """Audit a refused registration in its own unit of work (the attempt rolled back)."""
        try:
            async with self._uow() as uow:
                await uow.audit.record(
                    self._audit(
                        AuditOutcome.FAILURE, actor, self._clock.now(), details={"reason": reason}
                    )
                )
        except StorageUnavailableError as exc:
            await self._telemetry.storage_failed(OPERATION, exc, actor)
            return Failure(user_error(UserErrorCode.STORAGE_ERROR))
        await self._telemetry.registration_rejected(reason, actor)
        return Failure(user_error(reason))

    def _audit(
        self,
        outcome: AuditOutcome,
        actor: Actor,
        now: datetime,
        *,
        resource_id: str | None = None,
        details: dict[str, str] | None = None,
    ) -> AuditRecord:
        return AuditRecord(
            id=self._ids.new_id(),
            operation=OPERATION,
            outcome=outcome,
            actor=actor,
            occurred_at=now,
            resource_id=resource_id,
            details=details or {},
        )
