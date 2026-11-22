"""What every command shares: the project, its config, prompts, output and file generation."""

import contextlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from blitz_cli.config import BlitzConfig, ConfigError, load_config
from blitz_cli.edit import EditError, parse
from blitz_cli.project import Project, ProjectError, find_root, tidy
from blitz_cli.templates import TemplateError, TemplateSet, load

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class State:
    """Global options, set by the ``blitz`` callback."""

    root: Path | None = None
    interactive: bool | None = None
    _project: Project | None = field(default=None, repr=False)
    _config: BlitzConfig | None = field(default=None, repr=False)

    @property
    def is_interactive(self) -> bool:
        """``--interactive`` / ``--no-interactive``; otherwise only on a TTY outside CI."""
        if self.interactive is not None:
            return self.interactive
        return sys.stdin.isatty() and not os.environ.get("CI")


DryRun = Annotated[bool, typer.Option("--dry-run", help="Show what would change; write nothing.")]
Yes = Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")]
Tests = Annotated[
    bool | None,
    typer.Option("--tests/--no-tests", help="Generate tests.", show_default="[tool.blitz] tests"),
]
ServiceOpt = Annotated[
    str | None,
    typer.Option(
        help="Service to register with.",
        show_default="[tool.blitz] default-service",
        autocompletion=lambda incomplete: complete_services(incomplete),
    ),
]


def fail(message: str) -> typer.Exit:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def warn(message: str) -> None:
    typer.secho(f"warning: {message}", fg=typer.colors.YELLOW, err=True)


def state(ctx: typer.Context) -> State:
    obj = ctx.find_root().obj
    if not isinstance(obj, State):
        obj = ctx.find_root().obj = State()
    return obj


def project(ctx: typer.Context) -> Project:
    st = state(ctx)
    if st._project is None:
        try:
            st._project = Project(st.root.resolve() if st.root else find_root(Path.cwd()))
        except ProjectError as exc:
            raise fail(str(exc)) from exc
    return st._project


def config(ctx: typer.Context) -> BlitzConfig:
    st = state(ctx)
    if st._config is None:
        try:
            st._config = load_config(project(ctx).root)
        except ConfigError as exc:
            raise fail(str(exc)) from exc
    return st._config


def service_or_default(ctx: typer.Context, service: str | None) -> str:
    return service or config(ctx).default_service


def template_set(ctx: typer.Context, name: str) -> TemplateSet:
    try:
        return load(name, config(ctx).template_dirs)
    except TemplateError as exc:
        raise fail(str(exc)) from exc


def ask(
    ctx: typer.Context,
    text: str,
    check: Callable[[str], str | None],
    default: str | None = None,
    *,
    flag: str = "",
) -> str:
    """Prompt until ``check`` accepts the answer (it returns an error message or None).

    Non-interactive: the default is the answer, and without one the command fails,
    naming the argument or flag that supplies it.
    """
    if not state(ctx).is_interactive:
        if default is None:
            hint = f"; pass {flag}" if flag else ""
            raise fail(f"{text}: no answer in non-interactive mode{hint}")
        if error := check(default):
            raise fail(error)
        return default
    while True:
        answer = str(typer.prompt(text, default=default)).strip()
        error = check(answer)
        if error is None:
            return answer
        typer.secho(f"  {error}", fg=typer.colors.RED, err=True)


def confirm(ctx: typer.Context, text: str, *, default: bool = True, yes: bool = False) -> bool:
    """``yes`` or non-interactive with a ``True`` default → yes; non-interactive otherwise → no."""
    if yes:
        return True
    if not state(ctx).is_interactive:
        return default
    return typer.confirm(text, default=default)


def generate(
    ctx: typer.Context,
    set_name: str,
    values: dict[str, str],
    *,
    dry_run: bool,
    tests: bool | None = True,
) -> list[Path]:
    """Render a template set into the project. Refuses to overwrite a file, except that an
    existing empty file (a package ``__init__.py``) is left as it is."""
    proj = project(ctx)
    with_tests = config(ctx).tests if tests is None else tests
    try:
        files = template_set(ctx, set_name).render(values)
    except TemplateError as exc:
        raise fail(str(exc)) from exc
    if not with_tests:
        files = [f for f in files if f.path.parts[0] != "tests"]

    def keep_existing(path: Path, content: str) -> bool:
        target = proj.root / path
        return target.exists() and not content and not target.read_text().strip()

    clashes = [f.path for f in files if (proj.root / f.path).exists()]
    clashes = [
        p for p in clashes if not keep_existing(p, next(f for f in files if f.path == p).content)
    ]
    if clashes:
        raise fail(f"{clashes[0]} already exists; nothing written")
    written = []
    for file in files:
        if keep_existing(file.path, file.content):
            continue
        target = proj.root / file.path
        typer.echo(f"  {'would create' if dry_run else 'created'} {file.path}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content)
            written.append(target)
    return written


def write_edit(
    ctx: typer.Context, path: Path, new_text: str, *, dry_run: bool, what: str
) -> Path | None:
    """Write an edited file (or report it in a dry run); return it for ``finish``.

    An edited Python file must still parse: a broken edit fails instead of being written.
    """
    rel = project(ctx).rel(path)
    if path.exists() and path.read_text() == new_text:
        return None
    if path.suffix == ".py":
        try:
            parse(new_text, rel)
        except EditError as exc:
            raise fail(f"{exc}; nothing written to {rel}, edit it by hand") from exc
    typer.echo(f"  {'would update' if dry_run else 'updated'} {rel} ({what})")
    if dry_run:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text)
    return path


def finish(ctx: typer.Context, written: list[Path], next_step: str = "") -> None:
    """Format what was written and print the next step."""
    if warning := tidy(project(ctx).root, [p for p in written if p is not None]):
        warn(warning)
    if next_step:
        typer.echo(f"\nNext: {next_step}")


# ── shell completion (`blitz --install-completion`) ──────────────────────────


def _completion_project() -> Project | None:
    try:
        return Project(find_root(Path.cwd()))
    except ProjectError:
        return None


def _matching(names: list[str], incomplete: str) -> list[str]:
    return [n for n in names if n.startswith(incomplete)]


def complete_domains(incomplete: str) -> list[str]:
    proj = _completion_project()
    return _matching(proj.domains(), incomplete) if proj else []


def complete_services(incomplete: str) -> list[str]:
    proj = _completion_project()
    return _matching(proj.services(), incomplete) if proj else []


def _template_names() -> list[str]:
    from blitz_cli.templates import TEMPLATES_DIR, available

    proj = _completion_project()
    dirs = [TEMPLATES_DIR]
    if proj is not None:
        with contextlib.suppress(ConfigError):
            dirs = load_config(proj.root).template_dirs
    try:
        return [t.name for t in available(dirs)]
    except TemplateError:
        return []


def complete_templates(incomplete: str) -> list[str]:
    return _matching(_template_names(), incomplete)


def complete_integrations(incomplete: str) -> list[str]:
    names = [
        n.removeprefix("integration-") for n in _template_names() if n.startswith("integration-")
    ]
    return _matching(names, incomplete)
