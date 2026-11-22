from typing import Annotated, Any

from auth.dependency import get_auth_context
from fastapi import Depends

from .principal import Principal


def current_principal(principal: Annotated[Any, Depends(get_auth_context)]) -> Principal:
    if not isinstance(principal, Principal):
        # get_auth_context returns None when no provider is registered.
        msg = "no authenticated Principal: build the app with create_todo_app()"
        raise TypeError(msg)
    return principal


#: Route parameter that requires a valid API token (401 otherwise).
CurrentPrincipalDep = Annotated[Principal, Depends(current_principal)]
