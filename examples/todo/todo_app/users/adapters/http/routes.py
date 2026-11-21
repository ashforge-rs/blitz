from typing import Annotated

from deps import RequestContextDep
from fastapi import Depends, Request, Response, status
from returns.pipeline import is_successful
from returns.result import Result
from routing import ResultRouter
from state import get_domain

from todo_app.users.container import UsersDomain
from todo_app.users.entities import DisplayName, EmailAddress
from todo_app.users.use_cases import RegisterUser
from todo_app.web import IdempotencyKeyHeader, mark_replayed, request_actor

from .problems import UserProblem, to_problem
from .schemas import RegisteredUserResponse, RegisterUserBody


def _register_user(request: Request) -> RegisterUser:
    return get_domain(request, UsersDomain).register


RegisterUserDep = Annotated[RegisterUser, Depends(_register_user)]

router = ResultRouter(prefix="/users", tags=["users"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def register_user(
    body: RegisterUserBody,
    register: RegisterUserDep,
    ctx: RequestContextDep,
    response: Response,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Result[RegisteredUserResponse, UserProblem]:
    """Register a user.  The response holds their API token; it is not shown again.

    Retrying with the same ``Idempotency-Key`` returns the same user with a new
    token and revokes the one the failed attempt issued.
    """
    result = await register.execute(
        EmailAddress(body.email),
        DisplayName(body.name),
        request_actor(ctx),
        idempotency_key=idempotency_key,
    )
    if is_successful(result) and result.unwrap().replayed:
        mark_replayed(response)
    return result.map(RegisteredUserResponse.from_registration).alt(to_problem)
