from pathlib import Path

import pytest

from blitz_cli.project import Project, ProjectError, find_root

EMPTY = """\
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

DOMAINS: list[types.ModuleType] = []
"""


def _registry(root: Path, service: str, text: str) -> Path:
    path = root / "src" / "services" / service / "domains.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_find_root_walks_up(root):
    nested = root / "src" / "services" / "api"
    assert find_root(nested) == root


def test_find_root_outside_project(tmp_path):
    with pytest.raises(ProjectError):
        find_root(tmp_path)


def test_register_appends_import_and_entry(root):
    project = Project(root)
    assert project.register("api", "orders") is True
    text = project.registry("api").read_text()
    assert "from domains.example import domain as example_domain\n" in text
    assert "from domains.orders import domain as orders_domain\n" in text
    assert "    example_domain,\n    orders_domain,\n]" in text
    assert project.registered("api") == ["example", "orders"]


def test_register_is_idempotent(root):
    project = Project(root)
    project.register("api", "orders")
    assert project.register("api", "orders") is False
    assert project.registry("api").read_text().count("orders_domain,") == 1


def test_register_into_empty_list(root):
    path = _registry(root, "worker", EMPTY)
    Project(root).register("worker", "orders")
    text = path.read_text()
    assert "from domains.orders import domain as orders_domain\n\nif TYPE_CHECKING:" in text
    assert text.endswith("DOMAINS: list[types.ModuleType] = [\n    orders_domain,\n]\n")


def test_register_without_trailing_comma(root):
    path = _registry(root, "worker", EMPTY.replace("[]", "[\n    a_domain\n]"))
    Project(root).register("worker", "orders")
    assert "[\n    a_domain,\n    orders_domain,\n]" in path.read_text()


def test_register_missing_service(root):
    with pytest.raises(ProjectError, match="not found"):
        Project(root).register("worker", "orders")


def test_unregister_reverses_register(root):
    project = Project(root)
    before = project.registry("api").read_text()
    project.register("api", "orders")
    assert project.unregister("api", "orders") is True
    assert project.registry("api").read_text() == before
    assert project.unregister("api", "orders") is False


def test_unregister_single_line_list(root):
    path = _registry(
        root,
        "worker",
        "from domains.a import domain as a_domain\n"
        "from domains.b import domain as b_domain\n\n"
        "DOMAINS = [a_domain, b_domain]\n",
    )
    Project(root).unregister("worker", "a")
    assert path.read_text() == "from domains.b import domain as b_domain\n\nDOMAINS = [b_domain]\n"
