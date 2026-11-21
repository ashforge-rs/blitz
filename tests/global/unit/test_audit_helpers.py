import pytest
from loguru import logger

from audit.backend import AuditBackend, AuditEvent, AuditEventType, AuditResult, AuditSeverity
from audit.backends.loguru import LoguruAuditBackend
from audit.backends.multi import MultiAuditBackend
from audit.helpers import log_auth_event, log_operation, log_security_violation
from audit.integrity import NoIntegrity


class _Collector(AuditBackend):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def log(self, event: AuditEvent) -> None:
        self.events.append(event)


async def test_log_security_violation_is_critical_with_metadata():
    backend = _Collector()
    await log_security_violation(
        backend,
        NoIntegrity(),
        "rate_limit_exceeded",
        remote_addr="192.0.2.1:1",
        path="/x",
        extra_metadata={"limit": "1/minute"},
    )
    (event,) = backend.events
    assert event.event_type == AuditEventType.SECURITY_VIOLATION
    assert event.severity == AuditSeverity.CRITICAL
    assert event.result == AuditResult.VIOLATION
    assert event.metadata == {"violation_type": "rate_limit_exceeded", "limit": "1/minute"}


@pytest.mark.parametrize(
    ("allowed", "result", "severity"),
    [
        (True, AuditResult.SUCCESS, AuditSeverity.INFO),
        (False, AuditResult.DENIED, AuditSeverity.CRITICAL),
    ],
)
async def test_log_auth_event_maps_allowed(allowed, result, severity):
    backend = _Collector()
    await log_auth_event(
        backend, NoIntegrity(), "/orders", allowed=allowed, extra_metadata={"k": 1}
    )
    (event,) = backend.events
    assert (event.result, event.severity, event.metadata) == (result, severity, {"k": 1})


async def test_multi_backend_fans_out_in_order():
    first, second = _Collector(), _Collector()
    event = AuditEvent(event_type=AuditEventType.HTTP_REQUEST)
    await MultiAuditBackend([first, second]).log(event)
    assert first.events == [event]
    assert second.events == [event]


@pytest.mark.parametrize(
    ("event", "level"),
    [
        (AuditEvent(event_type=AuditEventType.HTTP_REQUEST, status_code=503), "ERROR"),
        (AuditEvent(event_type=AuditEventType.HTTP_REQUEST, status_code=404), "WARNING"),
        (AuditEvent(event_type=AuditEventType.HTTP_REQUEST, status_code=200), "INFO"),
        (
            AuditEvent(
                event_type=AuditEventType.SECURITY_VIOLATION, severity=AuditSeverity.CRITICAL
            ),
            "CRITICAL",
        ),
    ],
)
async def test_loguru_backend_level(event, level):
    records: list = []
    sink = logger.add(records.append, level="DEBUG", format="{message}")
    try:
        await LoguruAuditBackend().log(event)
    finally:
        logger.remove(sink)
    (message,) = records
    assert message.record["level"].name == level
    assert message.record["extra"]["audit"] is True


class _Ctx:
    request_id = "req-1"
    remote_addr = "192.0.2.1:1"
    path = "/v1/orders"

    def get(self, key, default=None):
        return {"principal": "alice"}.get(key, default)


@pytest.mark.parametrize(
    ("result", "severity"),
    [(AuditResult.SUCCESS, AuditSeverity.INFO), (AuditResult.FAILURE, AuditSeverity.WARNING)],
)
async def test_log_operation_fills_request_fields_from_ctx(result, severity):
    backend = _Collector()
    await log_operation(
        backend,
        NoIntegrity(),
        _Ctx(),  # type: ignore[arg-type]
        "orders.create",
        result=result,
        resource_id="o-1",
        extra_metadata={"total": 3},
    )
    (event,) = backend.events
    assert event.event_type == AuditEventType.ADMIN_ACTION
    assert event.result == result
    assert event.severity == severity
    assert event.principal == "alice"
    assert event.correlation_id == "req-1"
    assert event.remote_addr == "192.0.2.1:1"
    assert event.path == "/v1/orders"
    assert event.method == "orders.create"
    assert event.metadata == {"operation": "orders.create", "resource_id": "o-1", "total": 3}
