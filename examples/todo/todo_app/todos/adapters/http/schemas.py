"""Request and response bodies.  Validation is delegated to the value objects."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from todo_app.todos.entities import Title, Todo
from todo_app.todos.use_cases import TodoCreated

TitleField = Annotated[
    str,
    StringConstraints(max_length=Title.MAX_LENGTH),
    AfterValidator(lambda v: Title(v).value),
]


class CreateTodoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: TitleField


class TodoResponse(BaseModel):
    id: str
    owner_id: str
    title: str
    done: bool
    created_at: datetime

    @classmethod
    def from_created(cls, created: TodoCreated) -> TodoResponse:
        return cls.from_entity(created.todo)

    @classmethod
    def from_entity(cls, todo: Todo) -> TodoResponse:
        return cls(
            id=todo.id,
            owner_id=todo.owner_id,
            title=todo.title.value,
            done=todo.done,
            created_at=todo.created_at,
        )
