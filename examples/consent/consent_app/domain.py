"""The consent store as a blitz domain module: its router and its bootstrap hook."""

from typing import TYPE_CHECKING

from fastapi import APIRouter

from .adapters.http.routes import router
from .container import ConsentDomain, build_consent
from .settings import from_boot

if TYPE_CHECKING:
    from bootstrap import BootstrapContext


def make_router() -> APIRouter:
    return router


async def bootstrap(boot: BootstrapContext) -> ConsentDomain:
    settings = from_boot(boot)
    domain = await build_consent(settings)
    domain.start_reporting(settings.METRICS_REFRESH_SECONDS)
    return domain
