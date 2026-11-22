from typing import TYPE_CHECKING

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from bootstrap import BootstrapContext

#: Key under which create_todo_app() puts TodoSettings in ``extra_context``.
EXTRA_KEY = "todo_settings"


class TodoSettings(BaseSettings):
    """Settings this app adds; the boilerplate's own stay in ``config.Settings``."""

    model_config = SettingsConfigDict(
        env_prefix="TODO_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    #: SQLAlchemy URL.  SQLite (``sqlite+aiosqlite:///todo.db``) or Postgres
    #: (``postgresql+asyncpg://user:password@host/db``).  Secret: it may hold a password.
    DATABASE_URL: SecretStr = SecretStr("sqlite+aiosqlite:///todo.db")
    #: Postgres: how long to wait for a new connection, or for a free one in the pool.
    DB_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    #: SQLite only: how long a write waits for another connection's write lock.
    DB_BUSY_TIMEOUT_MS: int = Field(default=5_000, ge=0)
    #: Apply pending migrations when the app or CLI starts.  Convenient in development;
    #: in production set false and run ``todo db upgrade`` as a release step.
    DB_MIGRATE_ON_STARTUP: bool = True
    #: /health turns unhealthy (503) when an audit entry has waited longer than this.
    OUTBOX_MAX_AGE_SECONDS: float = Field(default=300, gt=0)
    #: How often expired idempotency records (older than 24 h) are purged.
    IDEMPOTENCY_PURGE_INTERVAL_SECONDS: float = Field(default=3600, gt=0)
    #: How often the business metrics (users, todos) are recounted from the database.
    METRICS_REFRESH_SECONDS: float = Field(default=15, gt=0)
    #: How often the audit outbox relay looks for undelivered entries.
    OUTBOX_POLL_INTERVAL_SECONDS: float = Field(default=0.5, gt=0)


def from_boot(boot: BootstrapContext) -> TodoSettings:
    """Return the TodoSettings that create_todo_app() handed to every bootstrap()."""
    settings = boot.extra.get(EXTRA_KEY)
    if not isinstance(settings, TodoSettings):
        msg = f"boot.extra[{EXTRA_KEY!r}] is not TodoSettings; build the app with create_todo_app()"
        raise TypeError(msg)
    return settings
