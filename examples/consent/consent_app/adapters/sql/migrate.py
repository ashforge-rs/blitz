"""``python -m consent_app.adapters.sql.migrate``: the release step that applies migrations."""

import asyncio

from consent_app.settings import ConsentSettings

from .database import Database
from .schema import upgrade


async def _main() -> None:
    settings = ConsentSettings()
    db = await Database.connect(
        settings.DATABASE_URL.get_secret_value(),
        connect_timeout_s=settings.DB_CONNECT_TIMEOUT_SECONDS,
    )
    try:
        await upgrade(db)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(_main())
    print("consent schema at head")
