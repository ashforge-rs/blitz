"""Route annotations FastAPI can't resolve fail at startup with a fix hint (AGENTS.md gotcha #2)."""

import types
from typing import TYPE_CHECKING

import pytest
from fastapi import APIRouter
from returns.result import Result

from routing import ResultRouter

if TYPE_CHECKING:
    # Deliberately typing-only: these names do not exist at runtime.
    from pydantic import BaseModel as Payload


def test_plain_router_with_typing_only_body_fails_create_app(make_app):
    router = APIRouter()

    # Without the check, FastAPI registers this and treats `body` as a required
    # query parameter — every request would get a 422.
    @router.post("/things")
    async def create(body: Payload) -> None: ...

    module = types.ModuleType("domains.things.domain")
    module.make_router = lambda: router  # type: ignore[attr-defined]

    with pytest.raises(NameError, match=r"'Payload'.*TYPE_CHECKING") as info:
        make_app(domains=[module])
    assert "test_route_annotations" in str(info.value)  # names the offending module


def test_nested_router_is_checked(make_app):
    inner = APIRouter()

    @inner.get("/deep")
    async def deep(q: Payload) -> None: ...

    outer = APIRouter()
    outer.include_router(inner, prefix="/inner")
    module = types.ModuleType("domains.nested.domain")
    module.make_router = lambda: outer  # type: ignore[attr-defined]

    with pytest.raises(NameError, match="'Payload'"):
        make_app(domains=[module])


def test_result_router_reports_typing_only_return_type():
    router = ResultRouter()
    with pytest.raises(NameError, match=r"'Payload'.*module level"):

        @router.get("/thing")
        async def get() -> Result[Payload, Exception]: ...


def test_runtime_imports_are_accepted(make_app):
    from pydantic import BaseModel

    class Body(BaseModel):
        name: str

    router = APIRouter()

    @router.post("/ok")
    async def create(body: Body) -> Body:
        return body

    module = types.ModuleType("domains.ok.domain")
    module.make_router = lambda: router  # type: ignore[attr-defined]
    make_app(domains=[module])
