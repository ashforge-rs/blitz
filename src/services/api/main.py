from __future__ import annotations

import uvicorn

from app import create_app
from config import get_settings

# ---------------------------------------------------------------------------
# Register domain modules here:
#
#   from domains.orders import domain as orders_domain
#   from domains.users  import domain as users_domain
#
#   app = create_app(settings=settings, domains=[orders_domain, users_domain])
#
# Each module must expose make_router() and async bootstrap(settings) -> Any.
# See CLAUDE.md for the full domain pattern.
# ---------------------------------------------------------------------------
from domains.example import domain as example_domain

settings = get_settings()
app = create_app(settings=settings, domains=[example_domain])


def main() -> None:
    uvicorn.run(
        "services.api.main:app",
        host="0.0.0.0",
        port=8000,
        workers=settings.WORKERS,
        loop="uvloop",
        http="httptools",
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
        reload=settings.ENVIRONMENT == "development",
    )


if __name__ == "__main__":
    main()
