import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from blitz_cli.main import app

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A minimal blitz project: pyproject.toml and the api service's registry."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[tool.ruff]\nline-length = 100\n'
    )
    api = tmp_path / "src" / "services" / "api"
    api.mkdir(parents=True)
    shutil.copy(REPO / "src" / "services" / "api" / "domains.py", api / "domains.py")
    return tmp_path


@pytest.fixture
def blitz(root: Path) -> Callable[..., Result]:
    runner = CliRunner()

    def run(*args: str, input: str | None = None) -> Result:
        # Answers on stdin mean a wizard run: force prompting (stdin is not a TTY here).
        mode = ["--interactive"] if input is not None else ["--no-interactive"]
        return runner.invoke(app, ["--root", str(root), *mode, *args], input=input)

    return run


#: Real project files the wiring generators and `blitz add` edit.
PROJECT_FILES = [
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    "docker-compose.yml",
    "src/app.py",
    "src/config.py",
    "src/middleware/stack.py",
    "src/audit/backends/__init__.py",
    "src/services/api/main.py",
    "src/services/api/domains.py",
    "src/services/api/Dockerfile",
]


@pytest.fixture
def full_root(tmp_path: Path) -> Path:
    """A copy of the real files the generators edit (no domains)."""
    for rel in PROJECT_FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    registry = tmp_path / "src/services/api/domains.py"
    registry.write_text(
        registry.read_text()
        .replace("from domains.example import domain as example_domain\n", "")
        .replace("    example_domain,\n", "")
    )
    return tmp_path


@pytest.fixture
def full(full_root: Path) -> Callable[..., Result]:
    runner = CliRunner()

    def run(*args: str, input: str | None = None) -> Result:
        mode = ["--interactive"] if input is not None else ["--no-interactive"]
        return runner.invoke(app, ["--root", str(full_root), *mode, *args], input=input)

    return run
