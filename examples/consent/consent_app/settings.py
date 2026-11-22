from typing import TYPE_CHECKING

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from consent_app.profiles import PROFILES, RegulationProfile

if TYPE_CHECKING:
    from bootstrap import BootstrapContext

#: Key under which create_consent_app() puts ConsentSettings in ``extra_context``.
EXTRA_KEY = "consent_settings"


class ConsentSettings(BaseSettings):
    """Settings this app adds; the boilerplate's own stay in ``config.Settings``."""

    model_config = SettingsConfigDict(
        env_prefix="CONSENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    #: Which regulation's consent rules apply to this deployment.
    PROFILE: str = "gdpr"
    #: Client systems allowed to call the API: ``client=sha256(key)``, comma-separated.
    #: Empty means no client can (every API call is 401).  ``make api-key CLIENT=…``.
    API_KEYS: SecretStr = SecretStr("")
    #: SQLAlchemy URL; secret because it may hold a password.
    DATABASE_URL: SecretStr = SecretStr("sqlite+aiosqlite:///consent.db")
    #: Migrate on startup (development); false in production, with ``make migrate`` instead.
    DB_MIGRATE_ON_STARTUP: bool = True
    #: Postgres: how long to wait for a new or pooled connection before failing.
    DB_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    #: How often the business metrics (consent states, ledger tallies) are recomputed.
    METRICS_REFRESH_SECONDS: float = Field(default=15.0, gt=0)

    @field_validator("PROFILE")
    @classmethod
    def _known_profile(cls, value: str) -> str:
        if value not in PROFILES:
            msg = f"unknown profile {value!r}; known: {', '.join(sorted(PROFILES))}"
            raise ValueError(msg)
        return value

    @property
    def profile(self) -> RegulationProfile:
        return PROFILES[self.PROFILE]


def from_boot(boot: BootstrapContext) -> ConsentSettings:
    settings = boot.extra.get(EXTRA_KEY)
    if not isinstance(settings, ConsentSettings):
        msg = f"boot.extra[{EXTRA_KEY!r}] is not ConsentSettings; use create_consent_app()"
        raise TypeError(msg)
    return settings
