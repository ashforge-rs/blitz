import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any

from loguru import logger

from bootstrap import BootstrapContext
from log.setup import configure_logging
from telemetry.setup import setup_telemetry

if TYPE_CHECKING:
    import types
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Application lifespan — startup and graceful shutdown.

    **Startup**
    - Configures Loguru (JSON in production, coloured in development).
    - Bootstraps every domain module (see :mod:`bootstrap`).

    **Shutdown**
    - Waits up to ``SHUTDOWN_TIMEOUT_SECONDS`` for in-flight requests to drain.
    - Closes bootstrapped domains (``await instance.aclose()``) in reverse order.
      A domain whose ``aclose()`` raises is logged and the rest still close.
    """
    settings = app.state.settings

    configure_logging(
        level=settings.LOG_LEVEL,
        json=settings.ENVIRONMENT == "production",
    )
    setup_telemetry(settings)
    logger.info("blitz starting up", environment=settings.ENVIRONMENT)

    # Ensure in_flight counter exists (also set by _InFlightMiddleware per request)
    if not hasattr(app.state, "in_flight"):
        app.state.in_flight = 0

    boot = BootstrapContext(
        settings=settings,
        audit_backend=app.state.audit_backend,
        audit_integrity=app.state.audit_integrity,
        extra=getattr(app.state, "extra_context", {}),
    )

    # The exit stack closes already-bootstrapped domains even when a later
    # bootstrap fails, so a startup error never leaks open pools.
    async with AsyncExitStack() as closers:
        for module in getattr(app.state, "_domain_modules", []):
            if hasattr(module, "bootstrap"):
                instance = await _bootstrap(module, boot)
                _register(app, module, instance)
                if callable(getattr(instance, "aclose", None)):
                    closers.push_async_callback(_close, module.__name__, instance)

        yield

        await _drain(app, settings.SHUTDOWN_TIMEOUT_SECONDS)

    logger.info("blitz shutdown complete")


async def _bootstrap(module: types.ModuleType, boot: BootstrapContext) -> object:
    try:
        instance: object = await module.bootstrap(boot)
    except Exception as exc:
        logger.error("domain bootstrap failed", domain=module.__name__, error=str(exc))
        raise
    logger.info("domain bootstrapped", domain=module.__name__)
    return instance


def _register(app: FastAPI, module: types.ModuleType, instance: object) -> None:
    by_type: dict[type[Any], object] = app.state.domains_by_type
    if type(instance) in by_type:
        msg = (
            f"{module.__name__}.bootstrap returned a {type(instance).__name__}, "
            "which another domain already registered — get_domain() looks domains up by type"
        )
        raise TypeError(msg)
    app.state.domains[module.__name__] = instance
    by_type[type(instance)] = instance


async def _close(name: str, instance: Any) -> None:
    try:
        await instance.aclose()
    except Exception as exc:  # noqa: BLE001 — one failing domain must not block the others
        logger.error("domain shutdown failed", domain=name, error=str(exc))
    else:
        logger.info("domain closed", domain=name)


async def _drain(app: FastAPI, deadline: float) -> None:
    logger.info("blitz shutting down — draining in-flight requests")
    elapsed = 0.0
    interval = 0.1

    while getattr(app.state, "in_flight", 0) > 0 and elapsed < deadline:
        await asyncio.sleep(interval)
        elapsed += interval

    remaining = getattr(app.state, "in_flight", 0)
    if remaining > 0:
        logger.warning(
            "Shutdown timeout reached — forcing close",
            in_flight=remaining,
            timeout=deadline,
        )
