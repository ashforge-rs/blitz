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
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    api = tmp_path / "src" / "services" / "api"
    api.mkdir(parents=True)
    shutil.copy(REPO / "src" / "services" / "api" / "domains.py", api / "domains.py")
    return tmp_path


@pytest.fixture
def blitz(root: Path) -> Callable[..., Result]:
    runner = CliRunner()

    def run(*args: str, input: str | None = None) -> Result:
        return runner.invoke(app, ["--root", str(root), *args], input=input)

    return run
