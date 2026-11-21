"""scripts/new_domain.py — naming, registration and generated output."""

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("new_domain", ROOT / "scripts" / "new_domain.py")
assert _spec
assert _spec.loader
new_domain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(new_domain)


@pytest.mark.parametrize(
    ("name", "entity"),
    [
        ("orders", "Order"),
        ("user_profiles", "UserProfile"),
        ("categories", "Category"),
        ("billing", "Billing"),
        ("address", "Address"),
    ],
)
def test_default_entity(name, entity):
    assert new_domain.default_entity(name) == entity


@pytest.fixture
def root(tmp_path: Path) -> Path:
    registry = tmp_path / "src" / "services" / "api"
    registry.mkdir(parents=True)
    shutil.copy(ROOT / "src" / "services" / "api" / "domains.py", registry / "domains.py")
    return tmp_path


def test_register_appends_import_and_entry(root):
    assert new_domain.register(root, "api", "orders") is None
    text = (root / "src/services/api/domains.py").read_text()
    assert "from domains.orders import domain as orders_domain\n" in text
    assert "    example_domain,\n    orders_domain,\n]" in text


def test_register_is_idempotent(root):
    new_domain.register(root, "api", "orders")
    new_domain.register(root, "api", "orders")
    assert (root / "src/services/api/domains.py").read_text().count("orders_domain,") == 1


def test_register_missing_service(root):
    assert "not found" in new_domain.register(root, "worker", "orders")


def test_generates_package_and_tests(root):
    assert new_domain.main(["orders", "--root", str(root)]) == 0
    domain = (root / "src/domains/orders/domain.py").read_text()
    assert "class OrdersDomain:" in domain
    assert "async def bootstrap(boot: BootstrapContext) -> OrdersDomain:" in domain
    assert "$" not in domain  # every placeholder substituted
    for tier in ("unit/test_service.py", "integration/test_routes.py", "fuzz/test_fuzz.py"):
        assert (root / "tests/domains/orders" / tier).exists()


def test_refuses_existing_domain(root):
    (root / "src/domains/orders").mkdir(parents=True)
    assert new_domain.main(["orders", "--root", str(root), "--no-register"]) == 1


@pytest.mark.parametrize("bad", ["Orders", "1orders", "order-items", "example"])
def test_rejects_bad_names(root, bad):
    with pytest.raises(SystemExit):
        new_domain.main([bad, "--root", str(root)])
