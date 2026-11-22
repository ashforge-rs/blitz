"""``blitz add <integration>``: wire a whole integration into the project in one step.

An integration is a template set named ``integration-<name>`` whose ``template.toml``
also declares what to wire (all optional):

- ``dependencies``: packages for ``uv add``;
- ``mypy_ignore``: untyped modules for the ``ignore_missing_imports`` override;
- ``[[settings]]``: ``name``, ``annotation``, ``default``, ``comment``, ``env`` (the
  ``.env.example`` line) — added to ``Settings`` and ``.env.example``;
- ``[compose]``: ``service`` and its ``yaml`` (indented under ``services:``);
- ``health_check`` + ``health_module``: added to the service's ``health_checks``;
- ``[domain]``: ``imports``, ``store`` and ``close`` snippets that ``--domain`` puts in a
  domain's ``bootstrap()`` in place of its ``InMemoryStore``.
"""

import re
import subprocess
import tomllib
from string import Template
from typing import TYPE_CHECKING, Annotated, Any

import typer

from blitz_cli.edit import EditError, add_class_field, add_import
from blitz_cli.templates import MANIFEST, TemplateError, available

from .code import inspect_domain
from .common import (
    DryRun,
    ServiceOpt,
    Tests,
    complete_domains,
    complete_integrations,
    config,
    fail,
    finish,
    generate,
    project,
    service_or_default,
    template_set,
    warn,
    write_edit,
)
from .doctor import _settings_fields
from .extend import _wire

if TYPE_CHECKING:
    from pathlib import Path

PREFIX = "integration-"
_STORE_LINE = re.compile(
    r"^    store: InMemoryStore\[str, (\w+)\] = InMemoryStore\(\)\n", re.MULTILINE
)
_RETURN_LINE = re.compile(r"^    return (\w+Domain)\(service=service\)\n", re.MULTILINE)
_MYPY_IGNORE = re.compile(
    r"(\[\[tool\.mypy\.overrides\]\]\nmodule = \[\n)"
    r"((?:  \"[^\"]+\",\n)*)"
    r"(\]\nignore_missing_imports = true)"
)


def _manifest(ctx: typer.Context, name: str) -> dict[str, Any]:
    """Merged manifest of the integration's layers (a project layer may override keys)."""
    merged: dict[str, Any] = {}
    for layer in template_set(ctx, f"{PREFIX}{name}").layers:
        path = layer / MANIFEST
        if path.exists():
            merged |= tomllib.loads(path.read_text())
    return merged


def _integrations(ctx: typer.Context) -> list[tuple[str, str]]:
    try:
        sets = available(config(ctx).template_dirs)
    except TemplateError as exc:
        raise fail(str(exc)) from exc
    return [(s.name.removeprefix(PREFIX), s.description) for s in sets if s.name.startswith(PREFIX)]


def add(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(
            help="Integration, e.g. redis. Omit to list them.", autocompletion=complete_integrations
        ),
    ] = None,
    domain: Annotated[
        list[str] | None,
        typer.Option(
            "--domain",
            "-d",
            autocompletion=complete_domains,
            help="Domain whose bootstrap() should use the integration's store instead of "
            "InMemoryStore. Repeatable; also works after the integration was added.",
        ),
    ] = None,
    service: ServiceOpt = None,
    skip_install: Annotated[
        bool, typer.Option("--skip-install", help="Do not run `uv add` for the dependencies.")
    ] = False,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """Add an integration: code, settings, compose service, health check and dependencies.

    With --domain, also switch domains to its store. Stores stay in memory while the
    setting is empty (tests, local runs without the service), so nothing breaks before
    the dependency is running.
    """
    if name is None:
        for integration, description in _integrations(ctx):
            typer.echo(f"{integration}: {description}")
        return
    known = [i for i, _ in _integrations(ctx)]
    if name not in known:
        raise fail(f"unknown integration {name!r} (available: {', '.join(known)})")
    proj = project(ctx)
    meta = _manifest(ctx, name)
    settings_meta: list[dict[str, str]] = meta.get("settings", [])
    config_py = proj.root / "src" / "config.py"
    existing_fields = _settings_fields(config_py) or set()
    already = bool(settings_meta) and all(s["name"] in existing_fields for s in settings_meta)
    written: list[Path | None] = []

    if already:
        typer.echo(f"  {name} is already set up; wiring domains only")
    else:
        written += generate(ctx, f"{PREFIX}{name}", {}, dry_run=dry_run, tests=tests)
        written += _add_settings(ctx, settings_meta, name, dry_run=dry_run)
        written.append(_add_compose(ctx, meta.get("compose"), dry_run=dry_run))
        written.append(_add_mypy_ignore(ctx, meta.get("mypy_ignore", []), dry_run=dry_run))
        if check := meta.get("health_check"):
            main = proj.services_dir / service_or_default(ctx, service) / "main.py"
            written.append(
                _wire(
                    ctx,
                    main,
                    [
                        ("import", f"from {meta['health_module']} import {check}"),
                        ("kwarg-list", "health_checks", check),
                    ],
                    dry_run=dry_run,
                    what=f"health_checks += {check}",
                )
            )
    for domain_name in domain or []:
        written.append(_wire_domain(ctx, meta.get("domain"), domain_name, name, dry_run=dry_run))

    deps: list[str] = meta.get("dependencies", []) if not already else []
    if deps and not dry_run and not skip_install:
        typer.echo(f"  uv add {' '.join(deps)}")
        result = subprocess.run(["uv", "add", *deps], cwd=proj.root, check=False)  # noqa: S603, S607
        if result.returncode != 0:
            warn(f"`uv add {' '.join(deps)}` failed; run it yourself")
    elif deps:
        typer.echo(f"  {'would run' if dry_run else 'run yourself:'} uv add {' '.join(deps)}")
    if not dry_run:
        setting = ", ".join(s["name"] for s in settings_meta) or "the settings"
        finish(
            ctx,
            [w for w in written if w],
            f"set {setting} (see .env.example), `docker compose up`, `make verify`",
        )


def _add_settings(
    ctx: typer.Context, settings: list[dict[str, str]], integration: str, *, dry_run: bool
) -> list[Path | None]:
    proj = project(ctx)
    config_py = proj.root / "src" / "config.py"
    env_example = proj.root / ".env.example"
    if not settings:
        return []
    text = config_py.read_text()
    existing = _settings_fields(config_py) or set()
    env_text = env_example.read_text() if env_example.exists() else ""
    env_lines: list[str] = []
    try:
        for setting in settings:
            if setting["name"] in existing:
                continue
            field = f"{setting['name']}: {setting['annotation']} = {setting['default']}"
            code = f"    # {setting['comment']}\n    {field}"
            text = add_class_field(text, "Settings", code)
            if "SecretStr" in setting["annotation"]:
                text = add_import(text, "from pydantic import SecretStr")
            if not re.search(rf"^#?\s*{setting['name']}=", env_text, re.MULTILINE):
                env_lines += [f"# {setting['comment']}", setting["env"]]
    except EditError as exc:
        raise fail(f"src/config.py: {exc}") from exc
    out = [
        write_edit(
            ctx, config_py, text, dry_run=dry_run, what=", ".join(s["name"] for s in settings)
        )
    ]
    if env_lines:
        block = (
            f"\n# {integration.capitalize()} (blitz add {integration})\n"
            + "\n".join(env_lines)
            + "\n"
        )
        out.append(
            write_edit(
                ctx,
                env_example,
                env_text.rstrip("\n") + "\n" + block,
                dry_run=dry_run,
                what="documented",
            )
        )
    return out


def _add_compose(
    ctx: typer.Context, compose: dict[str, str] | None, *, dry_run: bool
) -> Path | None:
    if not compose:
        return None
    path = project(ctx).root / "docker-compose.yml"
    if not path.exists():
        warn("no docker-compose.yml; compose service not added")
        return None
    text = path.read_text()
    if re.search(rf"^  {re.escape(compose['service'])}:\s*$", text, re.MULTILINE):
        return None
    match = re.search(r"^services:\s*\n", text, re.MULTILINE)
    if match is None:
        warn("docker-compose.yml has no top-level `services:`; add the service by hand")
        return None
    block = compose["yaml"].strip("\n") + "\n\n"
    text = text[: match.end()] + block + text[match.end() :]
    return write_edit(ctx, path, text, dry_run=dry_run, what=f"service {compose['service']}")


def _add_mypy_ignore(ctx: typer.Context, modules: list[str], *, dry_run: bool) -> Path | None:
    if not modules:
        return None
    path = project(ctx).root / "pyproject.toml"
    text = path.read_text()
    match = _MYPY_IGNORE.search(text)
    if match is None:
        warn(f"no mypy `ignore_missing_imports` override in pyproject.toml; add {modules} by hand")
        return None
    present = set(re.findall(r'"([^"]+)"', match.group(2)))
    new = "".join(f'  "{m}",\n' for m in modules if m not in present)
    if not new:
        return None
    text = text[: match.end(2)] + new + text[match.end(2) :]
    return write_edit(ctx, path, text, dry_run=dry_run, what=f"mypy ignores {', '.join(modules)}")


def _wire_domain(
    ctx: typer.Context,
    snippet: dict[str, Any] | None,
    domain: str,
    integration: str,
    *,
    dry_run: bool,
) -> Path | None:
    if not snippet:
        raise fail(f"integration {integration!r} has no store to wire into a domain")
    info = inspect_domain(project(ctx), domain)
    path = info.files["domain"]
    text = path.read_text()
    if f"from store.{integration} import" in text:
        typer.echo(f"  {domain} already uses {integration}")
        return None
    if "store: KeyValueStore[" in text:
        raise fail(f"src/domains/{domain}/domain.py already uses another store; switch it by hand")
    store = _STORE_LINE.search(text)
    ret = _RETURN_LINE.search(text)
    if store is None or ret is None:
        raise fail(
            f"src/domains/{domain}/domain.py: bootstrap() does not have the generated "
            "`store: InMemoryStore[str, X] = InMemoryStore()` / `return XDomain(service=service)` "
            "lines; wire the store by hand"
        )
    if "self.closers" not in text:
        raise fail(
            f"src/domains/{domain}/domain.py: {ret.group(1)} has no `closers` list to close "
            "the connection on shutdown; add one (see a newly generated domain) or wire by hand"
        )
    values = {
        "Entity": store.group(1),
        "name": domain,
        "Plural": ret.group(1).removesuffix("Domain"),
    }
    store_code = Template(snippet["store"].strip("\n")).substitute(values) + "\n"
    close_code = Template(snippet.get("close", "").strip("\n")).substitute(values)
    returned = f"    domain = {ret.group(1)}(service=service)\n"
    returned += (close_code + "\n" if close_code else "") + "    return domain\n"
    text = text[: ret.start()] + returned + text[ret.end() :]
    store = _STORE_LINE.search(text)
    if store is None:  # unreachable: the store line precedes the return line
        raise fail("internal error: store line moved")
    text = text[: store.start()] + store_code + text[store.end() :]
    for line in snippet.get("imports", []):
        text = add_import(text, line)
    return write_edit(ctx, path, text, dry_run=dry_run, what=f"bootstrap() uses {integration}")
