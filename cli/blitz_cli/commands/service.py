"""Services: ASGI apps under ``src/services/``."""

from typing import Annotated

import typer

from blitz_cli import naming

from .common import DryRun, fail, finish, generate, project

app = typer.Typer(help="Services: ASGI apps under src/services/.", no_args_is_help=True)


@app.command("new")
def service_new(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="snake_case service name, e.g. worker.")],
    dry_run: DryRun = False,
) -> None:
    """Scaffold an ASGI service (main.py, domains.py, Dockerfile) from the `service` template."""
    proj = project(ctx)
    if error := naming.check_name(name, "service"):
        raise fail(error)
    if (proj.services_dir / name).exists():
        raise fail(f"src/services/{name} already exists")
    written = generate(ctx, "service", {"service": name}, dry_run=dry_run)
    if not dry_run:
        finish(
            ctx,
            written,
            f"`make domain DOMAIN=<name> SERVICE={name}`, then `make dev SERVICE={name}`",
        )


@app.command("list")
def service_list(ctx: typer.Context) -> None:
    """List services and the domains each one serves."""
    proj = project(ctx)
    for service in proj.services():
        typer.echo(f"{service}: {', '.join(proj.registered(service)) or '(no domains)'}")
