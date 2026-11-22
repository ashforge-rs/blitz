"""`blitz routes`, `blitz openapi` and shell completion.

routes / openapi build the real app, so they run against this repository with its venv.
"""

import json

import pytest
from typer.testing import CliRunner

from blitz_cli.commands import common
from blitz_cli.main import app

from .conftest import REPO

needs_venv = pytest.mark.skipif(
    not (REPO / ".venv" / "bin" / "python").exists(), reason="the repository venv is needed"
)


def _repo(*args):
    return CliRunner().invoke(app, ["--root", str(REPO), "--no-interactive", *args])


@needs_venv
def test_routes_lists_domain_and_built_in_routes():
    result = _repo("routes", "--json")
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    paths = {(r["path"], tuple(r["methods"])) for r in rows}
    assert ("/health", ("GET",)) in paths
    example = [r for r in rows if r["module"].startswith("domains.example")]
    assert example
    assert all(r["path"].startswith("/v1/") for r in example)
    assert not any(r["path"] == "/docs" for r in rows)  # hidden without --all


@needs_venv
def test_routes_table_and_filters():
    table = _repo("routes", "--domain", "example").output
    assert table.splitlines()[0].split() == [
        "SERVICE",
        "METHOD",
        "PATH",
        "OWNER",
        "AUTH",
        "HANDLER",
    ]
    assert "/health" not in table
    assert "routes, 0 behind get_auth_context" in table
    assert "/docs" in _repo("routes", "--all").output
    assert _repo("routes", "--service", "nope").exit_code == 1


@needs_venv
def test_openapi_export(tmp_path):
    out = tmp_path / "openapi.json"
    result = _repo("openapi", "-o", str(out))
    assert result.exit_code == 0, result.output
    schema = json.loads(out.read_text())
    assert any(path.startswith("/v1/") for path in schema["paths"])  # domain routes included


@needs_venv
def test_openapi_against_itself_and_a_trimmed_copy(tmp_path):
    saved = tmp_path / "openapi.json"
    _repo("openapi", "-o", str(saved))
    same = _repo("openapi", "--against", str(saved), "--check")
    assert same.exit_code == 0, same.output
    assert "0 breaking" in same.output

    schema = json.loads(saved.read_text())
    schema["paths"]["/v1/gone"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    saved.write_text(json.dumps(schema))
    gone = _repo("openapi", "--against", str(saved), "--check")
    assert gone.exit_code == 1
    assert "GET /v1/gone  operation removed" in gone.output


@needs_venv
def test_openapi_diff_against_head():
    result = _repo("openapi", "--diff", "HEAD", "--json")
    assert result.exit_code == 0, result.output
    assert isinstance(json.loads(result.output), list)


def test_openapi_rejects_bad_input(tmp_path):
    assert _repo("openapi", "--service", "nope").exit_code == 1
    assert "not both" in _repo("openapi", "--diff", "HEAD", "--against", str(tmp_path)).output


# ── completion ───────────────────────────────────────────────────────────────


def test_completion_is_installable():
    output = CliRunner().invoke(app, ["--help"]).output
    assert "--install-completion" in output


def test_completers(blitz, root, monkeypatch):
    blitz("g", "d", "orders")
    blitz("service", "new", "worker")
    monkeypatch.chdir(root / "src")
    assert common.complete_domains("o") == ["orders"]
    assert common.complete_domains("") == ["orders"]  # the fixture has no example package
    assert common.complete_services("w") == ["worker"]
    assert "domain" in common.complete_templates("dom")
    assert common.complete_integrations("") == ["postgres", "redis"]


def test_completers_outside_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert common.complete_domains("") == []
    assert "redis" in common.complete_integrations("r")
