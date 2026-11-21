"""Request and response bodies.  Validation is delegated to the value objects,
so each rule exists once (in ``entities/``) and a violation is still a 422 here.
"""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from todo_app.users.entities import DisplayName, EmailAddress, User
from todo_app.users.use_cases import Registration

EmailField = Annotated[
    str,
    StringConstraints(max_length=EmailAddress.MAX_LENGTH),
    AfterValidator(lambda v: EmailAddress(v).value),
]
NameField = Annotated[
    str,
    StringConstraints(max_length=DisplayName.MAX_LENGTH),
    AfterValidator(lambda v: DisplayName(v).value),
]


class RegisterUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailField
    name: NameField


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime

    @classmethod
    def from_entity(cls, user: User) -> UserResponse:
        return cls(
            id=user.id, email=user.email.value, name=user.name.value, created_at=user.created_at
        )


class RegisteredUserResponse(BaseModel):
    """``api_token`` is shown only here; the server keeps its hash."""

    user: UserResponse
    api_token: str

    @classmethod
    def from_registration(cls, registration: Registration) -> RegisteredUserResponse:
        return cls(
            user=UserResponse.from_entity(registration.user), api_token=registration.api_token
        )
