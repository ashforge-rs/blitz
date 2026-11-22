from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from fastapi.telemetry import TelemetryConfig

    from config import Settings


def telemetry_config(settings: Settings) -> TelemetryConfig:
    """
    Build the ``telemetry=`` argument for ``FastAPI()``.

    FastAPI instruments requests natively and reads the global providers, so
    no separate instrumentor is needed.  ``Settings`` stays the single source
    of truth: FastAPI's own env-var exporter setup is turned off so that
    ``OTEL_ENABLED=false`` really is a no-op and ``setup_telemetry`` is the
    only place an exporter gets attached.
    """
    if not settings.OTEL_ENABLED:
        return {"tracing": False, "metrics": False, "logs": False, "auto_configure": False}
    return {"auto_configure": False}


def parse_otel_headers(raw: str) -> dict[str, str]:
    """Parse OTel-format headers ``"k1=v1,k2=v2"`` (values may contain ``=``)."""
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        key, sep, value = pair.partition("=")
        if sep and key.strip():
            headers[key.strip()] = value.strip()
    return headers


def setup_telemetry(settings: Settings) -> None:
    """
    Configure the global OpenTelemetry TracerProvider.

    When ``OTEL_ENABLED=false`` (default) this is a no-op and tracing adds
    zero overhead.  Set ``OTEL_ENABLED=true`` and point ``OTEL_ENDPOINT`` at
    any OTLP HTTP collector — Jaeger, Grafana Tempo, Datadog Agent,
    Honeycomb, etc. — and distributed traces start flowing.

    The tracer provider is set globally via ``trace.set_tracer_provider()``.
    FastAPI's native telemetry (configured in ``create_app`` through
    ``telemetry_config``) picks it up once it is set.
    """
    if not settings.OTEL_ENABLED:
        return

    resource = Resource.create(
        {
            SERVICE_NAME: settings.OTEL_SERVICE_NAME,
            SERVICE_VERSION: settings.OPENAPI_VERSION,
        }
    )

    provider = TracerProvider(resource=resource)

    if settings.OTEL_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_ENDPOINT,
            headers=parse_otel_headers(settings.OTEL_HEADERS.get_secret_value()) or None,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
