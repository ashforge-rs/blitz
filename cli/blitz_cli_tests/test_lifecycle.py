"""`blitz new` / `blitz update` and the rendering they share, on a small template repository."""

import subprocess
import tomllib

import pytest
from typer.testing import CliRunner

from blitz_cli import scaffold
from blitz_cli.commands.update import Outcome, plan
from blitz_cli.main import app
from blitz_cli.scaffold import Answers, Identity, Record, read_record, render, write_record

NOTES = "".join(f"line {i}\n" for i in range(1, 11))

TEMPLATE = {
    "pyproject.toml": (
        '[project]\nname = "blitz"\nversion = "0.2.0"\ndescription = "FastAPI boilerplate"\n'
        'requires-python = ">=3.15"\n\n[tool.ruff]\ntarget-version = "py315"\n\n'
        '[tool.mypy]\npython_version = "3.15"\n'
    ),
    "uv.lock": (
        'version = 1\nrequires-python = ">=3.15"\n\n[[package]]\nname = "blitz"\n'
        'version = "0.2.0"\nsource = { editable = "." }\n'
    ),
    ".release-please-manifest.json": '{\n    ".": "0.2.0"\n}\n',
    "src/config.py": (
        'class Settings:\n    OPENAPI_TITLE: str = "blitz"\n    OTEL_SERVICE_NAME: str = "blitz"\n'
    ),
    ".env.example": "OPENAPI_TITLE=blitz\n# OTEL_SERVICE_NAME=blitz\n",
    "README.md": "# blitz\n\nFastAPI boilerplate: clone, configure, extend.\n",
    "src/services/api/domains.py": "DOMAINS = []\n",
    "src/services/api/Dockerfile": (
        'FROM python:3.15-slim AS builder\nLABEL org.opencontainers.image.title="blitz-api"\n'
    ),
    "infra/variables.tf": (
        'variable "github_owner" {\n  type        = string\n  default     = "ashforge-rs"\n}\n\n'
        'variable "repository_name" {\n  type        = string\n  default     = "blitz"\n}\n'
    ),
    "infra/terraform.tfvars.example": (
        'github_owner    = "ashforge-rs"\nrepository_name = "blitz"\n'
    ),
    "infra/repository.tf": (
        'resource "github_repository" "this" {\n  name        = var.repository_name\n'
        '  description = "FastAPI boilerplate"\n}\n'
    ),
    ".github/CODEOWNERS": "* @ashforge-rs\npyproject.toml @ashforge-rs\n",
    ".github/workflows/ci.yml": 'env:\n  PYTHON_PRIMARY: "3.15"\n',
    "CHANGELOG.md": "# Changelog\n",
    "examples/todo/README.md": "# todo\n",
    "notes.txt": NOTES,
    "shared.txt": "keep\nchange me\nkeep\n",
    "doomed.txt": "the template will delete this\n",
    "edited-then-deleted.txt": "v1\n",
}


def _git(cwd, *args):
    return subprocess.run(  # noqa: S603 — git with test-controlled arguments
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "test@example.invalid")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")


@pytest.fixture
def template(tmp_path):
    repo = tmp_path / "template"
    for path, text in TEMPLATE.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    _git(repo, "-c", "init.defaultBranch=main", "init", "--quiet")
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "-m", "v1")
    return repo


def _recorded_commit(dest):
    record = read_record(dest / "pyproject.toml")
    assert record is not None
    return record.commit


def _invoke(*args):
    return CliRunner().invoke(app, ["--no-interactive", *args])


def _new(template, dest, *extra):
    result = _invoke(
        "new",
        str(dest),
        "--from",
        str(template),
        "--owner",
        "acme",
        "--description",
        "Orders API",
        *extra,
    )
    assert result.exit_code == 0, result.output
    return dest


# ── rendering ────────────────────────────────────────────────────────────────


def _rendered(**answers):
    files = {path: text.encode() for path, text in TEMPLATE.items()}
    return {p: d.decode() for p, d in render(files, Answers(**answers)).items()}


def test_identity_is_read_from_the_tree():
    files = {path: text.encode() for path, text in TEMPLATE.items()}
    assert Identity.of(files) == Identity("blitz", "ashforge-rs", "3.15")


def test_render_renames_everything():
    out = _rendered(name="my-api", description="Orders API", owner="acme")
    project = tomllib.loads(out["pyproject.toml"])["project"]
    assert project == {
        "name": "my-api",
        "version": "0.1.0",
        "description": "Orders API",
        "requires-python": ">=3.15",
    }
    assert 'name = "my-api"\nversion = "0.1.0"\nsource = { editable = "." }' in out["uv.lock"]
    assert '".": "0.1.0"' in out[".release-please-manifest.json"]
    assert 'OPENAPI_TITLE: str = "my-api"' in out["src/config.py"]
    assert 'OTEL_SERVICE_NAME: str = "my-api"' in out["src/config.py"]
    assert out[".env.example"] == "OPENAPI_TITLE=my-api\n# OTEL_SERVICE_NAME=my-api\n"
    assert out["README.md"].startswith("# my-api\n")
    assert 'image.title="my-api-api"' in out["src/services/api/Dockerfile"]
    assert 'default     = "acme"' in out["infra/variables.tf"]
    assert 'default     = "my-api"' in out["infra/variables.tf"]
    assert (
        out["infra/terraform.tfvars.example"]
        == 'github_owner    = "acme"\nrepository_name = "my-api"\n'
    )
    assert 'description = "Orders API"' in out["infra/repository.tf"]
    assert out[".github/CODEOWNERS"] == "* @acme\npyproject.toml @acme\n"
    assert out["notes.txt"] == NOTES  # unrelated files are untouched


def test_render_leaves_out_history_and_examples():
    assert "CHANGELOG.md" not in _rendered(name="my-api")
    assert "examples/todo/README.md" not in _rendered(name="my-api")
    assert "examples/todo/README.md" in _rendered(name="my-api", examples=True)


def test_render_python_version():
    out = _rendered(name="my-api", python="3.16")
    assert 'requires-python = ">=3.16"' in out["pyproject.toml"]
    assert 'target-version = "py316"' in out["pyproject.toml"]
    assert 'python_version = "3.16"' in out["pyproject.toml"]
    assert 'requires-python = ">=3.16"' in out["uv.lock"]
    assert out["src/services/api/Dockerfile"].startswith("FROM python:3.16-slim")
    assert 'PYTHON_PRIMARY: "3.16"' in out[".github/workflows/ci.yml"]
    assert 'requires-python = ">=3.15"' in _rendered(name="my-api")["pyproject.toml"]


def test_render_without_owner_keeps_the_template_owner():
    out = _rendered(name="my-api")
    assert out[".github/CODEOWNERS"] == TEMPLATE[".github/CODEOWNERS"]
    assert 'default     = "ashforge-rs"' in out["infra/variables.tf"]


@pytest.mark.parametrize(
    "answers",
    [
        {"name": "My_API"},
        {"name": "-api"},
        {"name": "my-api", "python": "3"},
        {"name": "my-api", "owner": "bad owner"},
        {"name": "my-api", "description": 'say "hi"'},
        {"name": "my-api", "description": "back\\slash"},
    ],
)
def test_invalid_answers(answers):
    with pytest.raises(scaffold.ScaffoldError):
        Answers(**answers).check()


def test_record_roundtrip_and_replace(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n\n[tool.blitz]\ntests = true\n')
    first = Record("https://example.invalid/t.git", "a" * 40, Answers(name="x", owner="acme"))
    write_record(pyproject, first)
    assert read_record(pyproject) == first
    second = Record(first.source, "b" * 40, first.answers)
    write_record(pyproject, second)
    assert read_record(pyproject) == second
    text = pyproject.read_text()
    assert text.count("[tool.blitz.template]") == 1
    assert tomllib.loads(text)["tool"]["blitz"]["tests"] is True


# ── new ──────────────────────────────────────────────────────────────────────


def test_new_creates_a_recorded_git_project(template, tmp_path):
    dest = _new(template, tmp_path / "my-api")
    assert tomllib.loads((dest / "pyproject.toml").read_text())["project"]["name"] == "my-api"
    assert not (dest / "CHANGELOG.md").exists()
    assert not (dest / "examples").exists()
    record = read_record(dest / "pyproject.toml")
    assert record is not None
    assert record.source == str(template)
    assert record.commit == _git(template, "rev-parse", "HEAD")
    assert record.answers == Answers(name="my-api", description="Orders API", owner="acme")
    assert _git(dest, "status", "--porcelain") == ""
    assert "start from the blitz template" in _git(dest, "log", "--format=%s")


def test_new_name_flag_and_ref(template, tmp_path):
    first = _git(template, "rev-parse", "HEAD")
    (template / "notes.txt").write_text("changed\n")
    _git(template, "commit", "--quiet", "-am", "v2")
    dest = _new(template, tmp_path / "dir", "--name", "orders", "--ref", first)
    assert _recorded_commit(dest) == first
    assert (dest / "notes.txt").read_text() == NOTES
    assert 'OPENAPI_TITLE: str = "orders"' in (dest / "src/config.py").read_text()


def test_new_ignores_uncommitted_template_changes(template, tmp_path):
    (template / "notes.txt").write_text("not committed\n")
    dest = _new(template, tmp_path / "my-api")
    assert (dest / "notes.txt").read_text() == NOTES


def test_new_refuses_a_non_empty_directory_and_bad_input(template, tmp_path):
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "x").write_text("")
    assert "not empty" in _invoke("new", str(tmp_path / "taken"), "--from", str(template)).output
    assert _invoke("new", str(tmp_path / "Bad_Name"), "--from", str(template)).exit_code == 1
    assert _invoke("new", str(tmp_path / "x"), "--from", str(tmp_path / "missing")).exit_code == 1
    assert (
        _invoke("new", str(tmp_path / "y"), "--from", str(template), "--ref", "nope").exit_code == 1
    )


def test_new_defaults_to_the_checkouts_commit_on_its_origin(template, tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "--quiet", "--bare", str(template), str(origin))
    checkout = tmp_path / "checkout"
    _git(tmp_path, "clone", "--quiet", str(origin), str(checkout))
    (checkout / "notes.txt").write_text("not pushed yet\n")
    _git(checkout, "commit", "--quiet", "-am", "local")
    monkeypatch.setattr("blitz_cli.commands.new.HOME_TEMPLATE", checkout)

    result = _invoke("new", str(tmp_path / "early"))
    assert result.exit_code == 1
    assert "does not have" in result.output
    assert not (tmp_path / "early").exists()

    _git(checkout, "push", "--quiet", "origin", "HEAD")
    pushed = _git(checkout, "rev-parse", "HEAD")
    _git(checkout, "commit", "--quiet", "--allow-empty", "-m", "later")
    _git(checkout, "push", "--quiet", "origin", "HEAD")
    _git(checkout, "reset", "--quiet", "--hard", pushed)  # origin's HEAD is now ahead
    result = _invoke("new", str(tmp_path / "pushed"))
    assert result.exit_code == 0, result.output
    record = read_record(tmp_path / "pushed" / "pyproject.toml")
    assert record is not None
    assert record.source == str(origin)
    assert record.commit == pushed
    assert (tmp_path / "pushed" / "notes.txt").read_text() == "not pushed yet\n"


def test_new_without_git(template, tmp_path):
    dest = _new(template, tmp_path / "my-api", "--no-git")
    assert not (dest / ".git").exists()


# ── update ───────────────────────────────────────────────────────────────────


def _template_v2(template):
    notes = NOTES.replace("line 1\n", "line 1 (template)\n")
    (template / "notes.txt").write_text(notes)
    (template / "shared.txt").write_text("keep\nchanged by the template\nkeep\n")
    (template / "doomed.txt").unlink()
    (template / "edited-then-deleted.txt").write_text("v2\n")
    (template / "new-in-template.txt").write_text("hello\n")
    (template / "README.md").write_text(TEMPLATE["README.md"] + "\nMore docs.\n")
    _git(template, "add", "--all")
    _git(template, "commit", "--quiet", "-m", "v2")
    return _git(template, "rev-parse", "HEAD")


def _update(dest, *args):
    return _invoke("--root", str(dest), "update", *args)


def test_update_merges_template_changes(template, tmp_path):
    dest = _new(template, tmp_path / "my-api")
    (dest / "notes.txt").write_text(NOTES.replace("line 10\n", "line 10 (project)\n"))
    (dest / "shared.txt").write_text("keep\nchanged by the project\nkeep\n")
    (dest / "edited-then-deleted.txt").unlink()
    _git(dest, "commit", "--quiet", "-am", "project changes")
    new_commit = _template_v2(template)

    result = _update(dest)
    assert result.exit_code == 1, result.output  # one conflict
    notes = (dest / "notes.txt").read_text()
    assert notes.startswith("line 1 (template)\n")
    assert notes.endswith("line 10 (project)\n")
    shared = (dest / "shared.txt").read_text()
    assert "<<<<<<< project" in shared
    assert "changed by the project" in shared
    assert "changed by the template" in shared
    assert not (dest / "doomed.txt").exists()
    assert (dest / "new-in-template.txt").read_text() == "hello\n"
    assert not (dest / "edited-then-deleted.txt").exists()  # kept deleted
    readme = (dest / "README.md").read_text()
    assert readme.startswith("# my-api\n")
    assert readme.endswith("More docs.\n")
    assert _recorded_commit(dest) == new_commit
    for line in (
        "merged     notes.txt",
        "CONFLICT",
        "removed    doomed.txt",
        "added      new-in-template.txt",
    ):
        assert line in result.output
    assert "deleted here; the template changed it" in result.output


def test_update_is_clean_when_the_project_did_not_diverge(template, tmp_path):
    dest = _new(template, tmp_path / "my-api")
    _template_v2(template)
    result = _update(dest)
    assert result.exit_code == 0, result.output
    assert (dest / "shared.txt").read_text() == "keep\nchanged by the template\nkeep\n"
    assert "<<<<<<<" not in (dest / "pyproject.toml").read_text()


def test_update_when_up_to_date(template, tmp_path):
    dest = _new(template, tmp_path / "my-api")
    result = _update(dest)
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_update_dry_run_and_dirty_tree(template, tmp_path):
    dest = _new(template, tmp_path / "my-api")
    _template_v2(template)
    before = (dest / "notes.txt").read_text()
    result = _update(dest, "--dry-run")
    assert result.exit_code == 0
    assert "would update" in result.output
    assert (dest / "notes.txt").read_text() == before

    (dest / "notes.txt").write_text("uncommitted\n")
    result = _update(dest)
    assert result.exit_code == 1
    assert "uncommitted changes" in result.output


def test_update_outside_git_says_so(template, tmp_path):
    dest = _new(template, tmp_path / "my-api", "--no-git")
    result = _update(dest)
    assert result.exit_code == 1
    assert "not a git work tree" in result.output


def test_update_needs_a_record(tmp_path):
    (tmp_path / "src/services").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    result = _update(tmp_path)
    assert result.exit_code == 1
    assert "blitz new" in result.output


def test_plan_outcomes():
    base = {"same": b"a", "touched": b"a", "both": b"a\n", "gone": b"x", "kept": b"x"}
    theirs = {"same": b"a", "touched": b"b", "both": b"b\n", "new": b"n", "kept": b"y"}
    ours = {"same": b"a", "touched": b"a", "both": b"c\n", "gone": b"x"}
    outcomes = {s.path: s.outcome for s in plan(base, theirs, ours)}
    assert outcomes == {
        "touched": Outcome.updated,
        "both": Outcome.conflict,
        "gone": Outcome.removed,
        "new": Outcome.added,
        "kept": Outcome.kept,
    }
