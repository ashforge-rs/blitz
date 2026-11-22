"""The template sets, built-in and the project's own (``[tool.blitz] templates``)."""

from pathlib import Path
from typing import Annotated

import typer

from blitz_cli.project import ProjectError, find_root
from blitz_cli.templates import TEMPLATES_DIR, TemplateError, available, load

from .common import config, fail, state

app = typer.Typer(help="The template sets generators render.", no_args_is_help=True)


def _search(ctx: typer.Context) -> list[Path]:
    """The project's template dirs when run inside a project, else only the built-in ones."""
    try:
        if state(ctx).root is None:
            find_root(Path.cwd())
    except ProjectError:
        return [TEMPLATES_DIR]
    return config(ctx).template_dirs


@app.command("list")
def template_list(ctx: typer.Context) -> None:
    """List the template sets; `(project)` marks sets the project overrides or adds."""
    try:
        sets = available(_search(ctx))
    except TemplateError as exc:
        raise fail(str(exc)) from exc
    for template_set_ in sets:
        own = any(not layer.is_relative_to(TEMPLATES_DIR) for layer in template_set_.layers)
        typer.echo(
            f"{template_set_.name}{' (project)' if own else ''}: {template_set_.description}"
        )


@app.command("show")
def template_show(
    ctx: typer.Context, name: Annotated[str, typer.Argument(help="Template set name.")]
) -> None:
    """Show a template set's placeholders and the files it generates (and where each comes from)."""
    try:
        shown = load(name, _search(ctx))
    except TemplateError as exc:
        raise fail(str(exc)) from exc
    typer.echo(f"{shown.name}: {shown.description}")
    typer.echo(f"placeholders: {', '.join(sorted(shown.placeholders())) or '(none)'}")
    for pattern in shown.sources():
        source = shown.files[pattern]
        origin = "" if source.is_relative_to(TEMPLATES_DIR) else "  (project)"
        typer.echo(f"  {pattern}{origin}")
