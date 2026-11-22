"""``blitz info`` (versions and layout) and ``blitz doctor`` (checks the project's own rules)."""

import ast
import json
import platform
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata
from typing import TYPE_CHECKING, Annotated

import typer

from blitz_cli.edit import EditError, class_named, function_names, parse

from .common import config, project

if TYPE_CHECKING:
    from pathlib import Path

#: Packages whose locked versions `blitz info` shows.
KEY_PACKAGES = ("fastapi", "starlette", "pydantic", "pydantic-settings", "uvicorn", "returns")
ENV_KEY = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def _locked_versions(root: Path) -> dict[str, str]:
    lock = root / "uv.lock"
    if not lock.exists():
        return {}
    packages = tomllib.loads(lock.read_text()).get("package", [])
    return {p["name"]: p.get("version", "?") for p in packages if "name" in p}


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not installed"


def info(ctx: typer.Context) -> None:
    """Show versions (CLI, Python, locked framework packages) and the project's layout."""
    proj = project(ctx)
    cfg = config(ctx)
    meta = tomllib.loads((proj.root / "pyproject.toml").read_text()).get("project", {})
    locked = _locked_versions(proj.root)
    rows = [
        ("Project", f"{meta.get('name', '?')} {meta.get('version', '')}".strip()),
        ("Root", str(proj.root)),
        ("blitz-cli", _version("blitz-cli")),
        ("CLI Python", platform.python_version()),
        ("Requires Python", str(meta.get("requires-python", "?"))),
        ("OS", f"{platform.system()} {platform.release()}"),
    ]
    rows += [(name, locked.get(name, "not locked")) for name in KEY_PACKAGES]
    rows += [
        ("Services", ", ".join(proj.services()) or "(none)"),
        ("Domains", ", ".join(proj.domains()) or "(none)"),
        ("Default service", cfg.default_service),
        ("Templates", str(cfg.templates) if cfg.templates else "built-in"),
        ("Generate tests", "yes" if cfg.tests else "no"),
    ]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        typer.echo(f"{label:<{width}} : {value}")


# ── doctor ───────────────────────────────────────────────────────────────────


class Level(StrEnum):
    error = "error"
    warning = "warning"
    note = "note"


@dataclass(frozen=True, slots=True)
class Finding:
    level: Level
    where: str
    message: str


def _check_domain_module(rel: str, text: str) -> list[Finding]:
    """The contract `create_app()` enforces (src/bootstrap.py), read statically."""
    try:
        tree = parse(text, rel)
    except EditError as exc:
        return [Finding(Level.error, rel, str(exc))]
    hooks = function_names(tree) & {"make_router", "bootstrap"}
    if not hooks:
        return [Finding(Level.error, rel, "defines neither make_router() nor bootstrap()")]
    findings = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "bootstrap":
            findings.append(Finding(Level.error, rel, "bootstrap must be `async def`"))
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "bootstrap":
            required = [a for a in node.args.args[: len(node.args.args) - len(node.args.defaults)]]
            if len(required) != 1:
                findings.append(
                    Finding(
                        Level.error,
                        rel,
                        "bootstrap must take one argument: (boot: BootstrapContext)",
                    )
                )
    return findings


def _settings_fields(config_py: Path) -> set[str] | None:
    try:
        tree = parse(config_py.read_text(), "src/config.py")
    except OSError, EditError:
        return None
    settings = class_named(tree, "Settings")
    if settings is None:
        return None
    return {
        n.target.id
        for n in settings.body
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id.isupper()
    }


def _import_check(root: Path, services: list[str]) -> list[Finding]:
    """Import every service's DOMAINS in the project's venv and run validate_domain_module."""
    python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        return [
            Finding(
                Level.warning, ".venv", "no project venv (run `uv sync`); import checks skipped"
            )
        ]
    script = (
        "import importlib, json, sys\n"
        "from bootstrap import validate_domain_module\n"
        "out = []\n"
        "for svc in sys.argv[1:]:\n"
        "    try:\n"
        "        mods = importlib.import_module(f'services.{svc}.domains').DOMAINS\n"
        "        for m in mods:\n"
        "            try: validate_domain_module(m)\n"
        "            except TypeError as e: out.append([svc, str(e)])\n"
        "    except Exception as e: out.append([svc, f'{type(e).__name__}: {e}'])\n"
        "print(json.dumps(out))\n"
    )
    result = subprocess.run(  # noqa: S603 — the project's own interpreter
        [str(python), "-c", script, *services],
        capture_output=True,
        text=True,
        cwd=root,
        env={"PYTHONPATH": str(root / "src"), "PATH": "", "ENVIRONMENT": "test"},
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stderr.strip().splitlines() or ["(no output)"])[-1]
        return [Finding(Level.error, "import", tail)]
    try:
        problems = json.loads(result.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError, IndexError:
        return [Finding(Level.error, "import", "could not read the import check's output")]
    return [Finding(Level.error, f"src/services/{svc}", msg) for svc, msg in problems]


def diagnose(root: Path, *, import_check: bool = False) -> list[Finding]:
    from blitz_cli.project import Project

    proj = Project(root)
    findings: list[Finding] = []
    domains = proj.domains()
    services = proj.services()

    for domain in domains:
        package = proj.domains_dir / domain
        rel = f"src/domains/{domain}"
        domain_py = package / "domain.py"
        if not domain_py.exists():
            findings.append(
                Finding(Level.error, rel, "no domain.py (the module services register)")
            )
        else:
            findings += _check_domain_module(f"{rel}/domain.py", domain_py.read_text())
        if not proj.services_serving(domain):
            findings.append(Finding(Level.warning, rel, "not registered with any service"))
        tests = proj.root / "tests" / "domains" / domain
        if not (tests / "unit").is_dir():
            findings.append(
                Finding(Level.warning, rel, f"no unit tests in tests/domains/{domain}/unit/")
            )
        for tier in ("integration", "fuzz"):
            if not (tests / tier).is_dir():
                findings.append(Finding(Level.note, rel, f"no {tier} tests"))

    for service in services:
        rel = f"src/services/{service}"
        folder = proj.services_dir / service
        for registered in proj.registered(service):
            if registered not in domains:
                findings.append(
                    Finding(Level.error, rel, f"registers missing domain {registered!r}")
                )
        if not (folder / "main.py").exists():
            findings.append(Finding(Level.error, rel, "no main.py (the ASGI app)"))
        dockerfile = folder / "Dockerfile"
        if not dockerfile.exists():
            findings.append(
                Finding(Level.warning, rel, "no Dockerfile (`blitz service new` makes one)")
            )
        else:
            targets = set(re.findall(r"services\.(\w+)\.main:app", dockerfile.read_text()))
            if targets - {service}:
                findings.append(
                    Finding(
                        Level.error,
                        f"{rel}/Dockerfile",
                        f"runs services.{sorted(targets - {service})[0]}.main:app",
                    )
                )

    settings = _settings_fields(proj.root / "src" / "config.py")
    env_example = proj.root / ".env.example"
    if settings is not None and env_example.exists():
        documented = set(ENV_KEY.findall(env_example.read_text()))
        for name in sorted(settings - documented):
            findings.append(
                Finding(Level.error, ".env.example", f"Settings.{name} is not documented")
            )

    if import_check:
        findings += _import_check(proj.root, services)
    return findings


_COLORS = {Level.error: typer.colors.RED, Level.warning: typer.colors.YELLOW, Level.note: None}


def doctor(
    ctx: typer.Context,
    import_check: Annotated[
        bool,
        typer.Option(
            "--import/--no-import",
            help="Also import every service's domains in the project venv and run the "
            "contract check create_app() runs.",
        ),
    ] = False,
    strict: Annotated[bool, typer.Option(help="Fail on warnings too.")] = False,
    notes: Annotated[bool, typer.Option("--notes/--no-notes", help="Show notes.")] = True,
) -> None:
    """Check the project's rules: domain contract, registration, tests, Dockerfiles, settings.

    Exits 1 on errors (and on warnings with --strict). Fast and static by default;
    `make verify` stays the full gate.
    """
    proj = project(ctx)
    config(ctx)  # a malformed [tool.blitz] is reported (and fails) here
    findings = diagnose(proj.root, import_check=import_check)
    shown = [f for f in findings if notes or f.level != Level.note]
    for finding in shown:
        label = typer.style(finding.level.value, fg=_COLORS[finding.level], bold=True)
        typer.echo(f"{label}: {finding.where}: {finding.message}")
    counts = {level: sum(f.level == level for f in findings) for level in Level}
    summary = ", ".join(f"{n} {level.value}{'s' if n != 1 else ''}" for level, n in counts.items())
    typer.echo(
        ("\n" if shown else "")
        + f"{len(proj.domains())} domains, {len(proj.services())} services: {summary}"
    )
    if counts[Level.error] or (strict and counts[Level.warning]):
        raise typer.Exit(code=1)
