"""Runtime proof that the CLI needs no web stack: run the real entry point and list
every module it imported (``python -X importtime``)."""

import json
import os
import subprocess
import sys

WEB = ("fastapi", "starlette", "uvicorn", "httpx", "todo_app.web", "todo_app.auth", "routing")


def _run_cli(db_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    # No PYTHONPATH: the installed package must run on its own.
    env = {"PATH": os.environ.get("PATH", ""), "TODO_DB_PATH": db_path}
    return subprocess.run(  # noqa: S603 — fixed arguments, our own interpreter
        [sys.executable, "-X", "importtime", "-m", "todo_app.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def _imported(stderr: str) -> set[str]:
    # importtime lines: "import time:  self [us] | cumulative | <indent>module"
    return {
        line.rsplit("|", 1)[1].strip()
        for line in stderr.splitlines()
        if line.startswith("import time:") and "|" in line
    }


def test_the_cli_runs_without_importing_any_web_code(db_path: str) -> None:
    result = _run_cli(db_path, "register", "--email", "ada@example.com", "--name", "Ada")

    assert result.returncode == 0, result.stderr[-2000:]
    assert json.loads(result.stdout)["user"]["email"] == "ada@example.com"

    modules = _imported(result.stderr)
    assert "todo_app.users.use_cases.register_user" in modules  # the probe works
    web = sorted(m for m in modules if m.startswith(WEB) or ".adapters.http" in m)
    assert web == [], f"the CLI imported web code: {web}"
