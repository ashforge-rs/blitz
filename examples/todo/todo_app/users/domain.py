"""The users context as a blitz domain module: its router and its bootstrap hook."""

from typing import TYPE_CHECKING

from fastapi import APIRouter

from todo_app.settings import from_boot

from .adapters.http import router
from .container import UsersDomain, build_users

if TYPE_CHECKING:
    from bootstrap import BootstrapContext

__all__ = ["UsersDomain", "bootstrap", "make_router"]


def make_router() -> APIRouter:
    return router


async def bootstrap(boot: BootstrapContext) -> UsersDomain:
    return await build_users(
        from_boot(boot), audit_backend=boot.audit_backend, audit_integrity=boot.audit_integrity
    )
