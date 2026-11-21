"""The dependency rule, enforced: a violation fails the build instead of a review.

Inner layers, per context: ``entities/`` ← ``ports/`` + ``use_cases/``.

- ``entities/`` imports only the standard library, the kernel and itself.
- ``ports/`` and ``use_cases/`` may add ``returns`` and their own context's
  entities, ports and use cases.  Never adapters, frameworks, drivers or blitz.
- Contexts don't import each other; only the composition root (``factory.py``)
  sees both.  The shared packages (kernel, auth, persistence, web) import no context.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # examples/todo, the import root
APP = ROOT / "todo_app"
CONTEXTS = ("users", "todos")
INNER = ("entities", "ports", "use_cases")

# Standard library, minus I/O and drivers that belong in adapters.
_STDLIB = sys.stdlib_module_names - {"sqlite3", "asyncio", "concurrent", "socket", "http"}


def _module_name(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path) -> list[str]:
    """Every module *path* imports, relative imports resolved to absolute names."""
    package = _module_name(path) if path.name == "__init__.py" else _module_name(path.parent)
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.append(node.module or "")
            else:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                found.append(".".join([*base, node.module] if node.module else base))
    return found


def _is_stdlib(module: str) -> bool:
    return module.split(".")[0] in _STDLIB


def _layer_files(context: str, layer: str) -> list[Path]:
    return sorted((APP / context / layer).rglob("*.py"))


def _ids(path: Path) -> str:
    return str(path.relative_to(APP))


ENTITY_FILES = [p for c in CONTEXTS for p in _layer_files(c, "entities")]
APPLICATION_FILES = [
    p for c in CONTEXTS for layer in ("ports", "use_cases") for p in _layer_files(c, layer)
]
KERNEL_FILES = sorted((APP / "kernel").rglob("*.py"))


@pytest.mark.parametrize("path", ENTITY_FILES + KERNEL_FILES, ids=_ids)
def test_entities_and_kernel_depend_on_nothing_outward(path: Path) -> None:
    own = _module_name(path.parent)
    for module in _imports(path):
        allowed = _is_stdlib(module) or module.startswith(("todo_app.kernel", own))
        assert allowed, f"{_ids(path)} imports {module!r}: entities may use only stdlib + kernel"


@pytest.mark.parametrize("path", APPLICATION_FILES, ids=_ids)
def test_ports_and_use_cases_stay_inside_their_context(path: Path) -> None:
    context = path.relative_to(APP).parts[0]
    inner = tuple(f"todo_app.{context}.{layer}" for layer in INNER)
    for module in _imports(path):
        allowed = (
            _is_stdlib(module)
            or module.split(".")[0] == "returns"
            or module.startswith(("todo_app.kernel", *inner))
        )
        assert allowed, f"{_ids(path)} imports {module!r}: inner layers must stay pure"


@pytest.mark.parametrize("context", CONTEXTS)
def test_contexts_do_not_import_each_other(context: str) -> None:
    others = tuple(f"todo_app.{c}" for c in CONTEXTS if c != context)
    for path in (APP / context).rglob("*.py"):
        for module in _imports(path):
            assert not module.startswith(others), (
                f"{_ids(path)} imports {module!r}; go through a port in auth/ "
                "or the composition root (factory.py)"
            )


SHARED = ("kernel", "auth", "persistence", "web")


@pytest.mark.parametrize("package", SHARED)
def test_shared_packages_are_independent_of_the_contexts(package: str) -> None:
    for path in (APP / package).rglob("*.py"):
        for module in _imports(path):
            assert not module.startswith(("todo_app.users", "todo_app.todos")), (_ids(path), module)


#: Web frameworks and blitz's HTTP layer (top-level packages under src/).
_WEB_PACKAGES = {"fastapi", "starlette", "uvicorn", "app", "deps", "routing", "state"}
#: This app's HTTP-side modules.
_WEB_MODULES = ("todo_app.web", "todo_app.auth", "todo_app.factory", "todo_app.main")


@pytest.mark.parametrize("path", sorted((APP / "cli").rglob("*.py")), ids=_ids)
def test_the_cli_driver_imports_no_web_code(path: Path) -> None:
    """Static half of the proof; ``todo_tests/cli/test_cli_imports.py`` checks it at runtime."""
    for module in _imports(path):
        where = f"{_ids(path)} imports {module!r}"
        assert module.split(".")[0] not in _WEB_PACKAGES, where
        assert not module.startswith(_WEB_MODULES), where
        assert ".adapters.http" not in module, where
        assert not module.endswith(".domain"), where  # blitz domain modules mount routers


def test_relative_imports_are_resolved() -> None:
    probe = APP / "users" / "use_cases" / "register_user.py"

    assert "todo_app.users.use_cases.errors" in _imports(probe)
    assert _module_name(APP / "users" / "entities" / "__init__.py") == "todo_app.users.entities"
