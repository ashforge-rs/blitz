"""``blitz routes``: every route each service serves, from the real app."""

import json
from typing import Annotated, Any

import typer

from blitz_cli.runner import APP_FOR_SERVICE, RunnerError, run_json

from .common import complete_services, fail, project

_SCRIPT = (
    APP_FOR_SERVICE
    + """
import json, sys
from starlette.routing import Mount
from auth.dependency import get_auth_context

def calls(dependant):
    for sub in dependant.dependencies:
        yield sub.call
        yield from calls(sub)

def walk(routes, prefix=""):
    for route in routes:
        if isinstance(route, Mount):
            yield from walk(route.routes, prefix + route.path)
        else:
            yield prefix, route

out = []
for service in sys.argv[1:]:
    for prefix, route in walk(app_for(service).routes):
        endpoint = getattr(route, "endpoint", None)
        dependant = getattr(route, "dependant", None)
        out.append({
            "service": service,
            "methods": sorted(set(getattr(route, "methods", None) or []) - {"HEAD"}),
            "path": prefix + route.path,
            "name": route.name,
            "module": getattr(endpoint, "__module__", "") or "",
            "auth": dependant is not None and any(c is get_auth_context for c in calls(dependant)),
            "in_schema": getattr(route, "include_in_schema", True),
        })
print(json.dumps(out))
"""
)


def _owner(module: str) -> str:
    """``domains.orders.domain`` → ``orders``; ``routes.health`` → ``(built-in)``."""
    parts = module.split(".")
    if len(parts) > 1 and parts[0] == "domains":
        return parts[1]
    return "(built-in)" if parts[0] in {"routes", "fastapi", "starlette"} else module


def routes(
    ctx: typer.Context,
    service: Annotated[
        list[str] | None,
        typer.Option(
            "--service",
            "-s",
            help="Only these services (repeatable).",
            autocompletion=complete_services,
        ),
    ] = None,
    domain: Annotated[str | None, typer.Option(help="Only this domain's routes.")] = None,
    show_all: Annotated[
        bool, typer.Option("--all", help="Include routes hidden from the schema (/docs, …).")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON instead of a table.")] = False,
) -> None:
    """List every route the services serve: method, path, owner, and whether it needs auth.

    Built from the real app (create_app() with each service's DOMAINS) in the project's
    venv, so prefixes, mounted routers and dependencies are exactly what runs. AUTH marks
    routes that depend on get_auth_context.
    """
    proj = project(ctx)
    services = service or proj.services()
    if unknown := [s for s in services if s not in proj.services()]:
        raise fail(f"unknown service {unknown[0]!r} (have: {', '.join(proj.services())})")
    try:
        found: list[dict[str, Any]] = run_json(proj.root, _SCRIPT, *services)
    except RunnerError as exc:
        raise fail(f"could not build the app: {exc}") from exc
    rows = [
        r
        for r in found
        if (show_all or r["in_schema"]) and (domain is None or _owner(r["module"]) == domain)
    ]
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        typer.echo("no routes")
        return
    table = [
        (
            r["service"],
            ",".join(r["methods"]) or "-",
            r["path"],
            _owner(r["module"]),
            "auth" if r["auth"] else "",
            r["name"],
        )
        for r in sorted(rows, key=lambda r: (r["service"], r["path"], r["methods"]))
    ]
    headers = ("SERVICE", "METHOD", "PATH", "OWNER", "AUTH", "HANDLER")
    widths = [max(len(str(row[i])) for row in [headers, *table]) for i in range(len(headers))]
    for row in [headers, *table]:
        typer.echo(
            "  ".join(
                str(cell).ljust(width) for cell, width in zip(row, widths, strict=True)
            ).rstrip()
        )
    protected = sum(1 for r in rows if r["auth"])
    typer.echo(f"\n{len(rows)} routes, {protected} behind get_auth_context")
