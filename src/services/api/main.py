import uvicorn

from app import create_app
from config import get_settings
from services.api.domains import DOMAINS

# Domain modules are listed in services/api/domains.py (`make domain DOMAIN=x`
# adds one). See CLAUDE.md for the domain contract.
settings = get_settings()
app = create_app(settings=settings, domains=DOMAINS)


def main() -> None:
    uvicorn.run(
        "services.api.main:app",
        host="0.0.0.0",  # noqa: S104 — container entry point; bind all interfaces
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
