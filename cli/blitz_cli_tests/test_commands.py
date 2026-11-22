"""The ``blitz`` commands, run against a throwaway project."""

import pytest

from blitz_cli.project import Project


def test_domain_new_generates_package_tests_and_registers(blitz, root):
    result = blitz("domain", "new", "orders")
    assert result.exit_code == 0, result.output
    domain = (root / "src/domains/orders/domain.py").read_text()
    assert "class OrdersDomain:" in domain
    assert "async def bootstrap(boot: BootstrapContext) -> OrdersDomain:" in domain
    for tier in ("unit/test_service.py", "integration/test_routes.py", "fuzz/test_fuzz.py"):
        assert (root / "tests/domains/orders" / tier).exists()
    routes = (root / "tests/domains/orders/integration/test_routes.py").read_text()
    assert "from services.api.domains import DOMAINS" in routes
    assert Project(root).registered("api") == ["example", "orders"]


def test_domain_new_custom_entity_and_service(blitz, root):
    assert blitz("service", "new", "worker").exit_code == 0
    result = blitz("domain", "new", "people", "--entity", "Person", "--service", "worker")
    assert result.exit_code == 0, result.output
    assert "class Person(BaseModel):" in (root / "src/domains/people/models.py").read_text()
    routes = (root / "tests/domains/people/integration/test_routes.py").read_text()
    assert "from services.worker.domains import DOMAINS" in routes
    assert Project(root).registered("worker") == ["people"]
    assert Project(root).registered("api") == ["example"]


def test_domain_new_dry_run_writes_nothing(blitz, root):
    before = (root / "src/services/api/domains.py").read_text()
    result = blitz("domain", "new", "orders", "--dry-run")
    assert result.exit_code == 0
    assert "would create src/domains/orders/domain.py" in result.output
    assert not (root / "src/domains").exists()
    assert (root / "src/services/api/domains.py").read_text() == before


def test_domain_new_no_register(blitz, root):
    assert blitz("domain", "new", "orders", "--no-register").exit_code == 0
    assert Project(root).registered("api") == ["example"]


def test_domain_new_refuses_existing(blitz, root):
    (root / "src/domains/orders").mkdir(parents=True)
    result = blitz("domain", "new", "orders", "--no-register")
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_domain_new_refuses_unknown_service_before_writing(blitz, root):
    result = blitz("domain", "new", "orders", "--service", "nope")
    assert result.exit_code == 1
    assert not (root / "src/domains/orders").exists()


def test_domain_new_rejects_bad_names(blitz):
    for args in (["Orders"], ["example"], ["orders", "--entity", "order"]):
        assert blitz("domain", "new", *args).exit_code == 1


def test_domain_list(blitz):
    blitz("domain", "new", "orders")
    blitz("domain", "new", "drafts", "--no-register")
    lines = blitz("domain", "list").output.splitlines()
    assert lines == ["drafts  (not registered)  [tests]", "orders  api  [tests]"]


def test_domain_remove(blitz, root):
    blitz("domain", "new", "orders")
    assert blitz("domain", "remove", "orders", input="n\n").exit_code == 1  # aborted
    assert (root / "src/domains/orders").exists()

    result = blitz("domain", "remove", "orders", "--yes")
    assert result.exit_code == 0, result.output
    assert not (root / "src/domains/orders").exists()
    assert not (root / "tests/domains/orders").exists()
    assert Project(root).registered("api") == ["example"]


def test_domain_remove_unknown(blitz):
    assert blitz("domain", "remove", "nope", "--yes").exit_code == 1


@pytest.mark.parametrize("name", [".", "..", "../..", "orders/..", "/etc", "orders\n"])
def test_domain_remove_refuses_paths(blitz, root, name):
    assert blitz("g", "d", "orders").exit_code == 0
    before = sorted(p for p in root.rglob("*"))
    result = blitz("domain", "remove", name, "--yes")
    assert result.exit_code == 1
    assert "invalid domain name" in result.output
    assert sorted(p for p in root.rglob("*")) == before


def test_service_new_and_list(blitz, root):
    result = blitz("service", "new", "worker")
    assert result.exit_code == 0, result.output
    service = root / "src/services/worker"
    assert "services.worker.main:app" in (service / "Dockerfile").read_text()
    assert 'ENV PATH="/app/.venv/bin:$PATH"' in (service / "Dockerfile").read_text()
    assert "from services.worker.domains import DOMAINS" in (service / "main.py").read_text()
    assert blitz("service", "list").output.splitlines() == ["api: example", "worker: (no domains)"]
    assert blitz("service", "new", "worker").exit_code == 1


def test_template_commands(blitz):
    assert "domain:" in blitz("template", "list").output
    shown = blitz("template", "show", "service").output
    assert "placeholders: service" in shown
    assert "src/services/$service/Dockerfile" in shown
    assert blitz("template", "show", "nope").exit_code == 1


def test_outside_project(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from blitz_cli.main import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["domain", "list"])
    assert result.exit_code == 1
    assert "no blitz project" in result.output


# ── crud ─────────────────────────────────────────────────────────────────────


def test_crud_with_flags_generates_fields(blitz, root):
    result = blitz("crud", "Product", "-f", "title:str", "-f", "price:float", "-f", "notes:str?")
    assert result.exit_code == 0, result.output
    models = (root / "src/domains/products/models.py").read_text()
    assert "    title: str\n    price: float\n    notes: str | None = None\n" in models
    assert "class CreateProductRequest(BaseModel):" in models
    assert "**request.model_dump()" in (root / "src/domains/products/service.py").read_text()
    assert Project(root).registered("api") == ["example", "products"]


def test_crud_rejects_bad_field(blitz, root):
    result = blitz("crud", "Product", "-f", "id:str")
    assert result.exit_code == 1
    assert "reserved" in result.output
    assert not (root / "src/domains").exists()


def test_crud_wizard(blitz, root):
    answers = [
        "Category",  # entity
        "",  # domain: accept "categories"
        "label",  # field 1
        "",  # type: str
        "",  # required: yes
        "rank",
        "number",  # not a type: asked again
        "int",
        "n",  # optional
        "",  # done
        "",  # generate: yes
    ]
    result = blitz("crud", input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    assert "Category (label:str, rank:int?) → src/domains/categories/" in result.output
    models = (root / "src/domains/categories/models.py").read_text()
    assert "    label: str\n    rank: int | None = None\n" in models


def test_crud_wizard_asks_service_when_there_are_several(blitz, root):
    blitz("service", "new", "worker")
    result = blitz("crud", input="Tag\n\nworker\nlabel\n\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert Project(root).registered("worker") == ["tags"]


def test_crud_wizard_needs_a_field_and_can_be_declined(blitz, root):
    result = blitz("crud", input="Tag\n\n\nlabel\n\n\n\nn\n")
    assert "add at least one field" in result.output
    assert result.exit_code == 1  # declined at "Generate?"
    assert not (root / "src/domains/tags").exists()


def test_crud_entity_given_asks_only_for_fields(blitz, root):
    result = blitz("crud", "Tag", "--dry-run", input="label\n\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert "Domain package" not in result.output
    assert "would create src/domains/tags/models.py" in result.output
    assert not (root / "src/domains").exists()


def test_domain_new_accepts_fields(blitz, root):
    assert blitz("domain", "new", "orders", "-f", "total:float").exit_code == 0
    assert "    total: float\n" in (root / "src/domains/orders/models.py").read_text()
