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
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        loop="uvloop",
        http="httptools",
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
        reload=settings.ENVIRONMENT == "development",
    )


if __name__ == "__main__":
    main()
