"""The dependency rule, enforced: a violation fails the build instead of a review.

- ``entities/`` imports only the standard library and itself.
- ``profiles/`` adds ``entities``; ``ports/`` too.
- ``use_cases/`` adds ``returns``, ``ports`` and ``profiles``.
- Nothing inner imports ``adapters``, a framework, a driver or blitz.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "consent_app"
_STDLIB = sys.stdlib_module_names - {"sqlite3", "asyncio", "concurrent", "socket", "http"}

ALLOWED = {
    "entities": ("consent_app.entities",),
    "profiles": ("consent_app.entities", "consent_app.profiles"),
    "ports": ("consent_app.entities", "consent_app.ports"),
    "use_cases": (
        "returns",
        "consent_app.entities",
        "consent_app.profiles",
        "consent_app.ports",
        "consent_app.use_cases",
    ),
}


def _module(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path) -> list[str]:
    package = _module(path) if path.name == "__init__.py" else _module(path.parent)
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                found.append(node.module or "")
            else:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                found.append(".".join([*base, node.module] if node.module else base))
    return found


CASES = [(layer, p) for layer in ALLOWED for p in sorted((APP / layer).rglob("*.py"))]


@pytest.mark.parametrize(
    ("layer", "path"), CASES, ids=lambda c: str(c) if isinstance(c, str) else c.name
)
def test_inner_layers_import_only_what_their_ring_allows(layer: str, path: Path) -> None:
    for module in _imports(path):
        ok = module.split(".")[0] in _STDLIB or module.startswith(ALLOWED[layer])
        assert ok, f"{path.relative_to(APP)} ({layer}) imports {module!r}"


def test_the_check_resolves_relative_imports() -> None:
    assert "consent_app.use_cases.errors" in _imports(APP / "use_cases" / "give_consent.py")
