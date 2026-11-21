from typing import TYPE_CHECKING

from returns.result import Failure, Result, Success

from todo_app.kernel import StorageUnavailableError
from todo_app.users.entities import hash_token, looks_like_token

from .errors import UserError, UserErrorCode, user_error

if TYPE_CHECKING:
    from todo_app.kernel import Actor
    from todo_app.users.entities import User
    from todo_app.users.ports import UsersUnitOfWorkFactory, UserTelemetry

OPERATION = "users.authenticate"


class AuthenticateToken:
    def __init__(self, uow: UsersUnitOfWorkFactory, telemetry: UserTelemetry) -> None:
        self._uow = uow
        self._telemetry = telemetry

    async def execute(self, token: str, actor: Actor) -> Result[User, UserError]:
        if not looks_like_token(token):
            return Failure(user_error(UserErrorCode.INVALID_TOKEN))
        try:
            async with self._uow(read_only=True) as uow:
                user = await uow.users.find_by_token_hash(hash_token(token))
        except StorageUnavailableError as exc:
            await self._telemetry.storage_failed(OPERATION, exc, actor)
            return Failure(user_error(UserErrorCode.STORAGE_ERROR))
        if user is None:
            return Failure(user_error(UserErrorCode.INVALID_TOKEN))
        return Success(user)
