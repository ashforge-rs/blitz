from typing import Annotated

from fastapi import Depends, Request, Response, status
from returns.pipeline import is_successful
from returns.result import Result

from deps import RequestContextDep
from routing import ResultRouter
from state import get_domain
from todo_app.auth import CurrentPrincipalDep
from todo_app.todos.container import TodosDomain
from todo_app.todos.entities import Title
from todo_app.todos.use_cases import CreateTodo
from todo_app.web import IdempotencyKeyHeader, mark_replayed, request_actor

from .problems import TodoProblem, to_problem
from .schemas import CreateTodoBody, TodoResponse


def _create_todo(request: Request) -> CreateTodo:
    return get_domain(request, TodosDomain).create


CreateTodoDep = Annotated[CreateTodo, Depends(_create_todo)]

router = ResultRouter(prefix="/todos", tags=["todos"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_todo(
    body: CreateTodoBody,
    principal: CurrentPrincipalDep,
    create: CreateTodoDep,
    ctx: RequestContextDep,
    response: Response,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Result[TodoResponse, TodoProblem]:
    """Create a todo owned by the caller.  Requires ``Authorization: Bearer <api token>``.

    Retrying with the same ``Idempotency-Key`` returns the todo created the first time.
    """
    result = await create.execute(
        principal.user_id,
        Title(body.title),
        request_actor(ctx, principal.user_id),
        idempotency_key=idempotency_key,
    )
    if is_successful(result) and result.unwrap().replayed:
        mark_replayed(response)
    return result.map(TodoResponse.from_created).alt(to_problem)
