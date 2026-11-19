import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_list(value: Any) -> Any:
    """Accept list env vars as comma-separated (``a,b``) or JSON (``["a","b"]``)."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith("["):
        return json.loads(stripped)
    return [item.strip() for item in stripped.split(",") if item.strip()]


# A list[str] setting that reads naturally from an env var: ``A,B,C``.
type StrList = Annotated[list[str], NoDecode, BeforeValidator(_split_list)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "production", "test"] = "development"
    LOG_LEVEL: str = "INFO"

    # Request controls
    MAX_REQUEST_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    REQUEST_TIMEOUT_SECONDS: float = 30.0

    # Rate limiting
    RATE_LIMIT: str = "100/minute"

    # CORS
    ALLOWED_ORIGINS: StrList = ["*"]
    # Set to True only when ALLOWED_ORIGINS lists explicit origins (not "*").
    # Browsers reject credentialed cross-origin requests to wildcard origins;
    # Starlette raises ValueError if you combine the two.
    CORS_ALLOW_CREDENTIALS: bool = False

    @model_validator(mode="after")
    def _validate_cors(self) -> Settings:
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.ALLOWED_ORIGINS:
            raise ValueError(
                "CORS_ALLOW_CREDENTIALS=true requires explicit ALLOWED_ORIGINS — "
                "wildcard '*' is not permitted with credentialed requests (RFC 6454 §6.1)"
            )
        return self

    # Trusted reverse-proxy IPs for X-Forwarded-For resolution.
    # Set to your load-balancer CIDR(s) in production; leave empty to trust only
    # the direct peer (safest default).
    # Example: TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12
    TRUSTED_PROXIES: StrList = []

    # Allowed Host header values. Empty list = allow all (dev default).
    # Set e.g. ALLOWED_HOSTS=api.example.com,staging.example.com in production.
    ALLOWED_HOSTS: StrList = []

    # URL prefix for every domain router (API versioning). Built-in operational
    # routes (/live, /health, /metrics, /docs) are never prefixed.
    # Set to "" to disable; must start with "/" otherwise.
    API_PREFIX: str = "/v1"

    @field_validator("API_PREFIX")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        value = value.rstrip("/")
        if value and not value.startswith("/"):
            raise ValueError("API_PREFIX must be empty or start with '/'")
        return value

    # OpenAPI / Swagger UI
    OPENAPI_TITLE: str = "blitz"
    OPENAPI_DESCRIPTION: str = (
        "FastAPI boilerplate.\n\n"
        "## Built-in endpoints\n\n"
        "| Endpoint | Description |\n"
        "|---|---|\n"
        '| `GET /live` | Liveness probe — always `200 {"status":"ok"}` |\n'
        "| `GET /health` | Readiness probe — `200`/`503` based on registered checks |\n"
        "| `GET /metrics` | Prometheus exposition format |\n"
    )
    OPENAPI_VERSION: str = "0.1.0"
    OPENAPI_CONTACT_NAME: str = ""
    OPENAPI_CONTACT_EMAIL: str = ""
    OPENAPI_CONTACT_URL: str = ""
    OPENAPI_LICENSE_NAME: str = ""
    OPENAPI_LICENSE_URL: str = ""
    OPENAPI_SERVERS: StrList = []  # comma-separated server URLs in .env

    # Prometheus metrics
    METRICS_ENDPOINT_ENABLED: bool = True
    METRICS_REQUIRE_AUTH: bool = False

    # Graceful shutdown
    SHUTDOWN_TIMEOUT_SECONDS: float = 30.0

    # Server workers — set > 1 for multi-process production deployments.
    # Matches the WEB_CONCURRENCY convention used by Heroku / Railway / Fly.io.
    # Note: MemoryStorage rate limiting is per-worker when WORKERS > 1.
    WORKERS: int = 1

    # OpenTelemetry distributed tracing
    # Set OTEL_ENABLED=true and OTEL_ENDPOINT to any OTLP HTTP collector URL
    # (Jaeger, Grafana Tempo, Datadog Agent, Honeycomb, etc.).
    # When disabled (default) tracing adds zero overhead.
    OTEL_ENABLED: bool = False
    OTEL_ENDPOINT: str = ""  # e.g. http://localhost:4318/v1/traces
    # Auth headers for hosted OTLP backends, in the OTel format
    # "key=value,key2=value2" (e.g. "x-honeycomb-team=<api-key>").
    #
    # Convention: every secret setting is a SecretStr — it is masked in repr,
    # logs, tracebacks and model_dump output. Unwrap it with get_secret_value
    # only at the point of use.
    OTEL_HEADERS: SecretStr = SecretStr("")
    OTEL_SERVICE_NAME: str = "blitz"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
