from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import create_app
from audit.backends.noop import NoopAuditBackend
from config import Settings
from telemetry.setup import telemetry_config


def _settings(**overrides) -> Settings:
    return Settings(ENVIRONMENT="test", LOG_LEVEL="WARNING", **overrides)


def test_telemetry_config_disabled_turns_everything_off():
    assert telemetry_config(_settings(OTEL_ENABLED=False)) == {
        "tracing": False,
        "metrics": False,
        "logs": False,
        "auto_configure": False,
    }


def test_telemetry_config_enabled_keeps_settings_as_source_of_truth():
    assert telemetry_config(_settings(OTEL_ENABLED=True)) == {"auto_configure": False}


async def test_requests_are_traced_natively_when_enabled():
    # Runs the enabled app first: lifespan installs the global TracerProvider,
    # which the SDK only allows once per process.
    exporter = InMemorySpanExporter()
    enabled = create_app(settings=_settings(OTEL_ENABLED=True), audit_backend=NoopAuditBackend())
    disabled = create_app(settings=_settings(OTEL_ENABLED=False), audit_backend=NoopAuditBackend())

    async with LifespanManager(enabled), LifespanManager(disabled):
        trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))

        async with AsyncClient(transport=ASGITransport(app=disabled), base_url="http://test") as c:
            assert (await c.get("/live")).status_code == 200
        assert exporter.get_finished_spans() == ()

        async with AsyncClient(transport=ASGITransport(app=enabled), base_url="http://test") as c:
            assert (await c.get("/live")).status_code == 200

    server_spans = [s for s in exporter.get_finished_spans() if s.kind is trace.SpanKind.SERVER]
    assert [s.name for s in server_spans] == ["GET /live"]
    assert server_spans[0].attributes["http.route"] == "/live"
    assert server_spans[0].resource.attributes["service.name"] == "blitz"
