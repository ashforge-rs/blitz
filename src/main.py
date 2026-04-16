from __future__ import annotations

import uvicorn

from app import create_app
from config import get_settings

# ---------------------------------------------------------------------------
# Register your domain modules here:
#
#   from orders import domain as orders_domain
#   from users import domain as users_domain
#
#   app = create_app(settings=settings, domains=[orders_domain, users_domain])
#
# Each module must expose make_router() and async bootstrap(settings) -> Any.
# See CLAUDE.md for the full domain pattern.
# ---------------------------------------------------------------------------

# Module-level app object used by Uvicorn: `uvicorn main:app`
# Tests should call create_app() directly — never import this `app` in tests.
settings = get_settings()
app = create_app(settings=settings)


def main() -> None:
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        workers=settings.WORKERS,
        loop="uvloop",
        http="httptools",
        log_level=settings.LOG_LEVEL.lower(),
        # uvicorn access logs are redundant — the audit middleware covers this.
        access_log=False,
        reload=settings.ENVIRONMENT == "development",
    )


if __name__ == "__main__":
    main()
