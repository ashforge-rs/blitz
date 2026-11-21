from typing import TYPE_CHECKING

from errors.domain import DomainFailure
from returns.pipeline import is_successful

from todo_app.auth.token_verifier import TokenVerifier
from todo_app.users.use_cases import UserErrorCode

from .http.problems import to_problem

if TYPE_CHECKING:
    from todo_app.kernel import Actor
    from todo_app.users.use_cases import AuthenticateToken


class UsersTokenVerifier(TokenVerifier):
    """Implements ``todo_app.auth.TokenVerifier`` with the AuthenticateToken use case.

    Returns the user id for a valid token and ``None`` for an unknown one.  An
    outage raises (→ 500), because it is not the caller's fault and must not
    look like a bad token (→ 401).
    """

    def __init__(self, authenticate: AuthenticateToken) -> None:
        self._authenticate = authenticate

    async def verify(self, token: str, actor: Actor) -> str | None:
        result = await self._authenticate.execute(token, actor)
        if is_successful(result):
            return result.unwrap().id
        error = result.failure()
        if error.code is UserErrorCode.INVALID_TOKEN:
            return None
        raise DomainFailure(to_problem(error))
