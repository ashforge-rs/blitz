"""``blitz`` — generate code from the predefined templates and manage the project's boilerplate."""

from pathlib import Path  # noqa: TC003 — typer reads option annotations at runtime
from typing import TYPE_CHECKING, Annotated

import typer

from .commands import code, domain, extend, integrations, service, template
from .commands import doctor as doctor_cmd
from .commands.common import State
from .commands.service import service_new

if TYPE_CHECKING:
    from collections.abc import Callable

app = typer.Typer(
    help="Generate code from blitz's templates and manage domains, services and integrations.",
    no_args_is_help=True,
    add_completion=False,
)
generate_app = typer.Typer(
    help="Generate code: `blitz g <generator> ...` (aliases in parentheses).", no_args_is_help=True
)


@app.callback()
def _options(
    ctx: typer.Context,
    root: Annotated[
        Path | None,
        typer.Option(help="Project root (default: nearest parent with src/services/)."),
    ] = None,
    interactive: Annotated[
        bool | None,
        typer.Option(
            "--interactive/--no-interactive",
            help="Ask questions. Default: only on a terminal and outside CI; otherwise "
            "defaults are used and a missing answer is an error.",
            show_default=False,
        ),
    ] = None,
) -> None:
    ctx.obj = State(root=root, interactive=interactive)


def _register(group: typer.Typer, func: Callable[..., None], name: str, *aliases: str) -> None:
    """Add ``func`` as ``name`` plus hidden ``aliases``; the help lists the aliases."""
    doc = (func.__doc__ or "").strip()
    summary, _, rest = doc.partition("\n")
    plural = "es" if len(aliases) > 1 else ""
    label = f"{summary} (alias{plural}: {', '.join(aliases)})" if aliases else summary
    group.command(name, help=f"{label}\n{rest}".strip())(func)
    for alias in aliases:
        group.command(alias, hidden=True, help=doc)(func)


# ── generators: `blitz generate` / `blitz g` ─────────────────────────────────

_register(generate_app, domain.domain_new, "domain", "d")
_register(generate_app, domain.crud, "resource", "res", "crud")
_register(generate_app, service_new, "service", "s")
_register(generate_app, code.endpoint, "endpoint", "e")
_register(generate_app, code.error_code, "error-code", "ec")
_register(generate_app, extend.auth_provider, "auth-provider", "auth")
_register(generate_app, extend.audit_backend, "audit-backend", "audit")
_register(generate_app, extend.health_check, "health-check", "hc")
_register(generate_app, extend.middleware, "middleware", "mw")
_register(generate_app, extend.route, "route", "r")
_register(generate_app, extend.metric, "metric", "m")
app.add_typer(generate_app, name="generate")
app.add_typer(generate_app, name="g", hidden=True)

# ── resources and project commands ───────────────────────────────────────────

app.add_typer(domain.app, name="domain")
app.command("crud")(domain.crud)
app.add_typer(service.app, name="service")
app.add_typer(template.app, name="template")
app.command("add")(integrations.add)
app.command("info")(doctor_cmd.info)
app.command("doctor")(doctor_cmd.doctor)


def main() -> None:
    app()
