from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from loguru import logger

from log.setup import configure_logging
from telemetry.setup import setup_telemetry

if TYPE_CHECKING:
    from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan — startup and graceful shutdown.

    **Startup**
    - Configures Loguru (JSON in production, coloured in development).
    - Initialises the in-flight request counter (``app.state.in_flight``).

    **Shutdown**
    - Waits up to ``SHUTDOWN_TIMEOUT_SECONDS`` for in-flight requests to drain.
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

    # --- Bootstrap domain modules ---
    # Each module may expose `async bootstrap(settings, **kwargs) -> Any`.
    # The returned instance is stored on app.state.domains[module.__name__].
    for module in getattr(app.state, "_domain_modules", []):
        if hasattr(module, "bootstrap"):
            try:
                instance = await module.bootstrap(settings)
                app.state.domains[module.__name__] = instance
                logger.info("domain bootstrapped", domain=module.__name__)
            except Exception as exc:
                logger.error("domain bootstrap failed", domain=module.__name__, error=str(exc))
                raise

    yield

    # --- Graceful shutdown ---
    logger.info("blitz shutting down — draining in-flight requests")
    deadline = settings.SHUTDOWN_TIMEOUT_SECONDS
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

    logger.info("blitz shutdown complete")
