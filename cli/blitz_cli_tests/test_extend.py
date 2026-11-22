"""Extension-point generators and their wiring, against copies of the real project files."""

import ast

import pytest


def _text(root, rel):
    text = (root / rel).read_text()
    ast.parse(text)
    return text


def test_auth_provider_is_wired(full, full_root):
    result = full("g", "auth", "jwt")
    assert result.exit_code == 0, result.output
    assert (full_root / "src/auth/providers/__init__.py").exists()
    assert "class JwtAuthProvider:" in _text(full_root, "src/auth/providers/jwt.py")
    main = _text(full_root, "src/services/api/main.py")
    assert "from auth.providers.jwt import JwtAuthProvider" in main
    assert "auth_provider=JwtAuthProvider()" in main
    assert (full_root / "tests/global/unit/test_auth_jwt.py").exists()


def test_second_auth_provider_is_not_wired_twice(full, full_root):
    full("g", "auth", "jwt")
    result = full("g", "auth", "api_key")
    assert result.exit_code == 0
    assert "already passes auth_provider" in result.output
    assert "ApiKeyAuthProvider" not in _text(full_root, "src/services/api/main.py")
    assert (full_root / "src/auth/providers/api_key.py").exists()


def test_audit_backend_is_wired(full, full_root):
    assert full("g", "audit", "warehouse").exit_code == 0
    assert "audit_backend=WarehouseAuditBackend()" in _text(full_root, "src/services/api/main.py")
    exports = _text(full_root, "src/audit/backends/__init__.py")
    assert "from audit.backends.warehouse import WarehouseAuditBackend" in exports
    assert '    "StdoutAuditBackend",\n    "WarehouseAuditBackend",\n]' in exports


def test_health_checks_accumulate(full, full_root):
    assert full("g", "hc", "s3").exit_code == 0
    assert full("g", "hc", "queue").exit_code == 0
    assert full("g", "hc", "queue").exit_code == 1  # file exists
    main = _text(full_root, "src/services/api/main.py")
    assert "health_checks=[check_s3, check_queue]" in main
    assert (full_root / "src/checks/__init__.py").exists()


def test_no_wire(full, full_root):
    before = (full_root / "src/services/api/main.py").read_text()
    assert full("g", "hc", "s3", "--no-wire").exit_code == 0
    assert (full_root / "src/services/api/main.py").read_text() == before


def test_wiring_into_missing_service_warns(full, full_root):
    result = full("g", "hc", "s3", "--service", "worker")
    assert result.exit_code == 0
    assert "not wired" in result.output
    assert (full_root / "src/checks/s3.py").exists()


def test_middleware_is_innermost(full, full_root):
    assert full("g", "mw", "timing").exit_code == 0
    stack = _text(full_root, "src/middleware/stack.py")
    assert "from middleware.timing import TimingMiddleware" in stack
    assert stack.index("add_middleware(TimingMiddleware)") < stack.index(
        "add_middleware(RequestContextMiddleware)"
    )


def test_route_is_included(full, full_root):
    assert full("g", "r", "status").exit_code == 0
    app_py = _text(full_root, "src/app.py")
    assert "status" in app_py.split("from routes import ")[1].splitlines()[0]
    assert "app.include_router(status.router)" in app_py
    assert '@router.get("/status"' in _text(full_root, "src/routes/status.py")


def test_metric_counter_and_histogram(full, full_root):
    assert full("g", "m", "orders_created_total", "--labels", "status,region").exit_code == 0
    assert full("g", "m", "checkout_seconds", "--type", "histogram").exit_code == 0
    metrics = _text(full_root, "src/metrics/custom.py")
    assert 'ORDERS_CREATED_TOTAL = counter(\n    "orders_created_total"' in metrics or (
        'ORDERS_CREATED_TOTAL = counter("orders_created_total"' in metrics
    )
    assert '["status", "region"]' in metrics
    assert "CHECKOUT_SECONDS = histogram(" in metrics
    assert "from metrics.registry import counter, histogram" in metrics


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["orders_created"], "must end in _total"),
        (["Bad"], "invalid metric name"),
        (["x_total", "--module", "registry"], "holds the helpers"),
        (["x_total", "--labels", "Bad"], "invalid label"),
    ],
)
def test_metric_rejects(full, args, error):
    result = full("g", "m", *args)
    assert result.exit_code == 1
    assert error in result.output


def test_metric_refuses_duplicate(full):
    assert full("g", "m", "x_total").exit_code == 0
    assert "already defined" in full("g", "m", "x_total").output
