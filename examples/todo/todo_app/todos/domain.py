"""The todos context as a blitz domain module: its router and its bootstrap hook."""

from typing import TYPE_CHECKING

from fastapi import APIRouter

from todo_app.settings import from_boot

from .adapters.http import router
from .container import TodosDomain, build_todos

if TYPE_CHECKING:
    from bootstrap import BootstrapContext

__all__ = ["TodosDomain", "bootstrap", "make_router"]


def make_router() -> APIRouter:
    return router


async def bootstrap(boot: BootstrapContext) -> TodosDomain:
    return await build_todos(
        from_boot(boot), audit_backend=boot.audit_backend, audit_integrity=boot.audit_integrity
    )
