"""`blitz g ...`: aliases, --no-crud, --no-tests, non-interactive mode, endpoint, error-code."""

import ast

import pytest

from blitz_cli.project import Project


def _parses(path):
    ast.parse(path.read_text())
    return path.read_text()


@pytest.mark.parametrize("alias", ["domain", "d"])
def test_generate_domain_alias(blitz, root, alias):
    assert blitz("g", alias, "orders").exit_code == 0
    assert (root / "src/domains/orders/domain.py").exists()


@pytest.mark.parametrize("alias", ["resource", "res", "crud"])
def test_generate_resource_alias(blitz, root, alias):
    result = blitz("generate", alias, "Product", "-f", "title:str")
    assert result.exit_code == 0, result.output
    assert "title: str" in (root / "src/domains/products/models.py").read_text()


def test_aliases_listed_in_help(blitz):
    output = blitz("g", "--help").output
    assert "alias: d" in output
    assert "aliases: res, crud" in output


def test_no_crud_domain(blitz, root):
    result = blitz("g", "d", "billing", "--no-crud")
    assert result.exit_code == 0, result.output
    domain = _parses(root / "src/domains/billing/domain.py")
    assert "@_router" not in domain
    assert "async def create" not in (root / "src/domains/billing/service.py").read_text()
    assert (root / "tests/domains/billing/unit/test_service.py").exists()
    assert not (root / "tests/domains/billing/integration").exists()
    assert "blitz g endpoint billing" in result.output


def test_no_tests(blitz, root):
    assert blitz("g", "d", "orders", "--no-tests").exit_code == 0
    assert (root / "src/domains/orders/domain.py").exists()
    assert not (root / "tests").exists()


def test_generated_domain_closes_what_bootstrap_opened(blitz, root):
    blitz("g", "d", "orders")
    domain = (root / "src/domains/orders/domain.py").read_text()
    assert "self.closers: list[Callable[[], Awaitable[object]]] = []" in domain
    assert "for close in reversed(self.closers):" in domain


# ── non-interactive ──────────────────────────────────────────────────────────


def test_crud_without_entity_fails_non_interactive(blitz, root):
    result = blitz("crud")  # the fixture passes --no-interactive
    assert result.exit_code == 1
    assert "pass ENTITY" in result.output


def test_crud_non_interactive_uses_default_fields(blitz, root):
    assert blitz("crud", "Tag").exit_code == 0
    assert "    name: str\n" in (root / "src/domains/tags/models.py").read_text()


def test_remove_needs_yes_non_interactive(blitz, root):
    blitz("g", "d", "orders")
    result = blitz("domain", "remove", "orders")
    assert result.exit_code == 1
    assert "--yes" in result.output
    assert (root / "src/domains/orders").exists()


def test_ci_env_disables_prompts(root, monkeypatch):
    from typer.testing import CliRunner

    from blitz_cli.main import app

    monkeypatch.setenv("CI", "true")
    result = CliRunner().invoke(app, ["--root", str(root), "crud"], input="Tag\n")
    assert result.exit_code == 1
    assert "non-interactive" in result.output


# ── endpoint ─────────────────────────────────────────────────────────────────


@pytest.fixture
def orders(blitz, root):
    assert blitz("g", "d", "orders").exit_code == 0
    return root / "src/domains/orders"


def test_item_endpoint(blitz, root, orders):
    result = blitz("g", "e", "orders", "cancel")
    assert result.exit_code == 0, result.output
    service = _parses(orders / "service.py")
    assert "async def cancel(self, order_id: str, ctx: RequestContext)" in service
    assert 'await self._audit_op(ctx, "orders.cancel", order_id)' in service
    domain = _parses(orders / "domain.py")
    assert '@_router.post("/{order_id}/cancel")' in domain
    assert domain.index("def cancel_order") < domain.index("def make_router")
    test = (root / "tests/domains/orders/integration/test_cancel.py").read_text()
    assert '"/v1/orders/missing/cancel"' in test


def test_collection_endpoint_precedes_item_routes(blitz, orders):
    assert blitz("g", "e", "orders", "search", "--collection", "--method", "get").exit_code == 0
    domain = (orders / "domain.py").read_text()
    assert '@_router.get("/search")' in domain
    assert domain.index('"/search"') < domain.index('"/{order_id}"')
    service = (orders / "service.py").read_text()
    assert "return await self.list_all(ctx)" in service  # GET: no audit event


def test_delete_endpoint_returns_no_body(blitz, orders):
    assert blitz("g", "e", "orders", "archive", "--method", "delete").exit_code == 0
    domain = (orders / "domain.py").read_text()
    assert "status_code=status.HTTP_204_NO_CONTENT" in domain
    assert ".map(lambda _: None)" in domain


def test_endpoint_on_bare_domain(blitz, root):
    blitz("g", "d", "billing", "--no-crud")
    assert blitz("g", "e", "billing", "charge").exit_code == 0
    domain = _parses(root / "src/domains/billing/domain.py")
    assert "from .dependencies import BillingServiceDep" in domain


def test_endpoint_refuses_duplicates_and_unknown_domain(blitz, orders):
    assert blitz("g", "e", "orders", "cancel").exit_code == 0
    assert "already exists" in blitz("g", "e", "orders", "cancel").output
    assert blitz("g", "e", "nope", "cancel").exit_code == 1
    assert blitz("g", "e", "orders", "Bad-Name").exit_code == 1


def test_endpoint_dry_run(blitz, orders):
    before = (orders / "service.py").read_text()
    result = blitz("g", "e", "orders", "cancel", "--dry-run")
    assert "would update src/domains/orders/service.py" in result.output
    assert (orders / "service.py").read_text() == before


def test_endpoint_without_service_has_no_test(blitz, root):
    blitz("g", "d", "drafts", "--no-register")
    result = blitz("g", "e", "drafts", "publish")
    assert "no test" in result.output
    assert not (root / "tests/domains/drafts/integration/test_publish.py").exists()


# ── error code ───────────────────────────────────────────────────────────────


def test_error_code(blitz, orders):
    result = blitz("g", "ec", "orders", "out_of_stock", "--status", "409")
    assert result.exit_code == 0, result.output
    errors = _parses(orders / "errors.py")
    assert '    STORAGE_ERROR = "storage_error"\n    OUT_OF_STOCK = "out_of_stock"\n' in errors
    assert "        OrderErrorCode.OUT_OF_STOCK: 409,\n    }" in errors
    assert "already exists" in blitz("g", "ec", "orders", "out_of_stock").output


@pytest.mark.parametrize("status", ["200", "600"])
def test_error_code_status_range(blitz, orders, status):
    assert blitz("g", "ec", "orders", "gone", "--status", status).exit_code == 1


def test_project_layout_untouched_by_failed_endpoint(blitz, root, orders):
    before = {p: p.read_text() for p in orders.glob("*.py")}
    blitz("g", "e", "orders", "Bad-Name")
    assert {p: p.read_text() for p in orders.glob("*.py")} == before
    assert Project(root).registered("api") == ["example", "orders"]


def test_keyword_names_are_rejected(blitz, root, orders):
    before = (orders / "service.py").read_text()
    result = blitz("g", "e", "orders", "return")
    assert result.exit_code == 1
    assert "Python keyword" in result.output
    assert (orders / "service.py").read_text() == before
    assert "Python keyword" in blitz("g", "d", "import").output
    assert "Python keyword" in blitz("g", "d", "things", "--entity", "None").output
    assert not (root / "src/domains/import").exists()


def test_endpoint_with_an_existing_test_writes_nothing(blitz, root, orders):
    test = root / "tests/domains/orders/integration/test_cancel.py"
    test.write_text("# hand-written\n")
    before = {p: p.read_text() for p in orders.glob("*.py")}
    result = blitz("g", "e", "orders", "cancel")
    assert result.exit_code == 1
    assert "nothing written" in result.output
    assert {p: p.read_text() for p in orders.glob("*.py")} == before


def test_domain_with_an_uneditable_registry_writes_nothing(blitz, root):
    (root / "src/services/api/domains.py").write_text("DOMAINS = list()\n")
    result = blitz("g", "d", "orders")
    assert result.exit_code == 1
    assert "nothing written" in result.output
    assert not (root / "src/domains/orders").exists()
    assert not (root / "tests/domains/orders").exists()
