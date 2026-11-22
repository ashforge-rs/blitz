"""Run a snippet inside the project's own environment (its venv, ``src/`` on the path).

The CLI has its own venv without FastAPI or the app, so anything that needs the real
app (routes, the OpenAPI schema, the domain contract) runs there and prints JSON.
"""

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

#: Builds the app for one service the way the tests do: no .env, no audit output.
APP_FOR_SERVICE = """
import importlib
from audit.backends.noop import NoopAuditBackend
from app import create_app
from config import Settings

def app_for(service):
    domains = importlib.import_module(f"services.{service}.domains").DOMAINS
    settings = Settings(_env_file=None, ENVIRONMENT="development")
    return create_app(settings=settings, domains=domains, audit_backend=NoopAuditBackend())
"""


class RunnerError(Exception):
    """The project's environment is missing or the snippet failed."""


def project_python(root: Path) -> Path:
    python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        raise RunnerError(f"no project venv at {root / '.venv'}; run `uv sync` in {root}")
    return python


def run_json(root: Path, script: str, *args: str, src: Path | None = None) -> Any:
    """Run ``script`` with the project's interpreter; it must print one JSON document last.

    ``src`` replaces ``<root>/src`` on the path (an older checkout of the same project).
    """
    env = {
        "PYTHONPATH": str(src or root / "src"),
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "ENVIRONMENT": "development",
    }
    result = subprocess.run(  # noqa: S603 — the project's own interpreter
        [str(project_python(root)), "-c", script, *args],
        capture_output=True,
        text=True,
        cwd=root,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines() or ["(no output)"]
        raise RunnerError(lines[-1])
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RunnerError("the project script printed no JSON") from exc
