from typing import TYPE_CHECKING

from pydantic import Field
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

    DB_PATH: str = "todo.db"
    DB_BUSY_TIMEOUT_MS: int = Field(default=5_000, ge=0)
    #: How often the audit outbox relay looks for undelivered entries.
    OUTBOX_POLL_INTERVAL_SECONDS: float = Field(default=0.5, gt=0)


def from_boot(boot: BootstrapContext) -> TodoSettings:
    """Return the TodoSettings that create_todo_app() handed to every bootstrap()."""
    settings = boot.extra.get(EXTRA_KEY)
    if not isinstance(settings, TodoSettings):
        msg = f"boot.extra[{EXTRA_KEY!r}] is not TodoSettings; build the app with create_todo_app()"
        raise TypeError(msg)
    return settings
