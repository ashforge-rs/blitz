"""Generators for the app's extension points (see AGENTS.md, Extension points)."""

import json
import re
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

import typer

from blitz_cli import naming
from blitz_cli.edit import (
    EditError,
    add_call_kwarg,
    add_import,
    add_to_all,
    insert_after_line,
    insert_before_line,
)

from .common import (
    DryRun,
    ServiceOpt,
    Tests,
    fail,
    finish,
    generate,
    project,
    service_or_default,
    warn,
    write_edit,
)

if TYPE_CHECKING:
    from pathlib import Path

Wire = Annotated[
    bool, typer.Option("--wire/--no-wire", help="Also register it where the app picks it up.")
]
Name = Annotated[str, typer.Argument(help="snake_case name, e.g. jwt or redis.")]


def _values(name: str, kind: str) -> dict[str, str]:
    if error := naming.check_name(name, kind):
        raise fail(error)
    return {
        "slug": name,
        "Pascal": naming.pascal(name),
        "words": name.replace("_", " ").capitalize(),
        "route": name.replace("_", "-"),
    }


def _wire(
    ctx: typer.Context, path: Path, edits: list[tuple[str, ...]], *, dry_run: bool, what: str
) -> Path | None:
    """Apply ``(kind, *args)`` edits to ``path``; on failure warn and leave the file as it is."""
    proj = project(ctx)
    if not path.exists():
        warn(f"not wired: {proj.rel(path)} not found; {what} by hand")
        return None
    text = path.read_text()
    try:
        for kind, *args in edits:
            if kind == "import":
                text = add_import(text, args[0])
            elif kind == "kwarg":
                text = add_call_kwarg(text, "create_app", args[0], args[1])
            elif kind == "kwarg-list":
                text = add_call_kwarg(text, "create_app", args[0], args[1], to_list=True)
            elif kind == "after":
                text = insert_after_line(text, args[0], args[1])
            elif kind == "before":
                text = insert_before_line(text, args[0], args[1])
            elif kind == "export":
                text = add_to_all(text, args[0])
    except EditError as exc:
        warn(f"not wired: {proj.rel(path)}: {exc}; {what} by hand")
        return None
    return write_edit(ctx, path, text, dry_run=dry_run, what=what)


def _main(ctx: typer.Context, service: str | None) -> Path:
    return project(ctx).services_dir / service_or_default(ctx, service) / "main.py"


def _done(ctx: typer.Context, written: list[Path | None], next_step: str, *, dry_run: bool) -> None:
    if not dry_run:
        finish(ctx, [w for w in written if w is not None], next_step)


def auth_provider(
    ctx: typer.Context,
    name: Name,
    service: ServiceOpt = None,
    wire: Wire = True,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """AuthProvider in src/auth/providers/<name>.py, passed to the service's create_app().

    It denies every request until authenticate() verifies something. Protect routes
    with Depends(get_auth_context).
    """
    values = _values(name, "auth provider")
    written: list[Path | None] = list(
        generate(ctx, "auth-provider", values, dry_run=dry_run, tests=tests)
    )
    cls = f"{values['Pascal']}AuthProvider"
    if wire:
        written.append(
            _wire(
                ctx,
                _main(ctx, service),
                [
                    ("import", f"from auth.providers.{name} import {cls}"),
                    ("kwarg", "auth_provider", f"{cls}()"),
                ],
                dry_run=dry_run,
                what=f"auth_provider={cls}()",
            )
        )
    _done(
        ctx,
        written,
        f"implement {cls}.authenticate(); add Depends(get_auth_context) to routes",
        dry_run=dry_run,
    )


def audit_backend(
    ctx: typer.Context,
    name: Name,
    service: ServiceOpt = None,
    wire: Wire = True,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """AuditBackend in src/audit/backends/<name>.py, passed to the service's create_app().

    It forwards to Loguru until log() writes to the real target.
    """
    values = _values(name, "audit backend")
    written: list[Path | None] = list(
        generate(ctx, "audit-backend", values, dry_run=dry_run, tests=tests)
    )
    cls = f"{values['Pascal']}AuditBackend"
    written.append(
        _wire(
            ctx,
            project(ctx).root / "src" / "audit" / "backends" / "__init__.py",
            [("import", f"from audit.backends.{name} import {cls}"), ("export", cls)],
            dry_run=dry_run,
            what=f"export {cls}",
        )
    )
    if wire:
        written.append(
            _wire(
                ctx,
                _main(ctx, service),
                [
                    ("import", f"from audit.backends.{name} import {cls}"),
                    ("kwarg", "audit_backend", f"{cls}()"),
                ],
                dry_run=dry_run,
                what=f"audit_backend={cls}()",
            )
        )
    _done(ctx, written, f"write events to the target in {cls}.log()", dry_run=dry_run)


def health_check(
    ctx: typer.Context,
    name: Name,
    service: ServiceOpt = None,
    wire: Wire = True,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """Readiness check in src/checks/<name>.py, added to the service's health_checks."""
    values = _values(name, "health check")
    written: list[Path | None] = list(
        generate(ctx, "health-check", values, dry_run=dry_run, tests=tests)
    )
    func = f"check_{name}"
    if wire:
        written.append(
            _wire(
                ctx,
                _main(ctx, service),
                [
                    ("import", f"from checks.{name} import {func}"),
                    ("kwarg-list", "health_checks", func),
                ],
                dry_run=dry_run,
                what=f"health_checks += {func}",
            )
        )
    _done(ctx, written, f"probe the dependency in {func}(); see it in GET /health", dry_run=dry_run)


def middleware(
    ctx: typer.Context,
    name: Name,
    wire: Wire = True,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """Pure-ASGI middleware in src/middleware/<name>.py, registered in stack.py.

    It is added innermost (next to the handler), where the request context exists.
    Move the add_middleware() line in stack.py to run it earlier.
    """
    values = _values(name, "middleware")
    written: list[Path | None] = list(
        generate(ctx, "middleware", values, dry_run=dry_run, tests=tests)
    )
    cls = f"{values['Pascal']}Middleware"
    if wire:
        written.append(
            _wire(
                ctx,
                project(ctx).root / "src" / "middleware" / "stack.py",
                [
                    ("import", f"from middleware.{name} import {cls}"),
                    (
                        "before",
                        "app.add_middleware(RequestContextMiddleware)",
                        f"app.add_middleware({cls})",
                    ),
                ],
                dry_run=dry_run,
                what=f"add_middleware({cls}), innermost",
            )
        )
    _done(ctx, written, f"fill in {cls}.__call__()", dry_run=dry_run)


def route(
    ctx: typer.Context,
    name: Name,
    wire: Wire = True,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """Operational route GET /<name> in src/routes/<name>.py, included in create_app().

    For business endpoints use a domain (`blitz g endpoint`); routes here are not under /v1.
    """
    values = _values(name, "route")
    written: list[Path | None] = list(generate(ctx, "route", values, dry_run=dry_run, tests=tests))
    if wire:
        written.append(
            _wire(
                ctx,
                project(ctx).root / "src" / "app.py",
                [
                    ("import", f"from routes import {name}"),
                    (
                        "after",
                        "app.include_router(health.router)",
                        f"app.include_router({name}.router)",
                    ),
                ],
                dry_run=dry_run,
                what=f"include_router({name}.router)",
            )
        )
    _done(ctx, written, f"shape the response in src/routes/{name}.py", dry_run=dry_run)


# ── metric ───────────────────────────────────────────────────────────────────


class MetricType(StrEnum):
    counter = "counter"
    histogram = "histogram"


_METRIC_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def metric(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Prometheus name, e.g. orders_created_total.")],
    type_: Annotated[MetricType, typer.Option("--type", help="Metric type.")] = MetricType.counter,
    labels: Annotated[
        str, typer.Option(help="Comma-separated label names, e.g. status,region.")
    ] = "",
    description: Annotated[str | None, typer.Option("--description", help="HELP text.")] = None,
    module: Annotated[
        str, typer.Option(help="Module under src/metrics/ to define it in.")
    ] = "custom",
    dry_run: DryRun = False,
) -> None:
    """Define a Prometheus metric in src/metrics/<module>.py with metrics.registry.

    Counters must end in _total; histograms of durations should end in _seconds.
    """
    if not _METRIC_RE.match(name):
        raise fail(f"invalid metric name {name!r}: use snake_case, e.g. orders_created_total")
    if type_ == MetricType.counter and not name.endswith("_total"):
        raise fail(f"counter {name!r} must end in _total (Prometheus naming)")
    if error := naming.check_name(module, "metrics module"):
        raise fail(error)
    if module == "registry":
        raise fail("module `registry` holds the helpers; pick another --module")
    label_list = [label.strip() for label in labels.split(",") if label.strip()]
    if bad := [label for label in label_list if not _METRIC_RE.match(label)]:
        raise fail(f"invalid label {bad[0]!r}: use snake_case")

    path = project(ctx).root / "src" / "metrics" / f"{module}.py"
    text = path.read_text() if path.exists() else ""
    constant = name.upper()
    if re.search(rf"^{constant}\b", text, re.MULTILINE) or f'"{name}"' in text:
        raise fail(f"{name} is already defined in src/metrics/{module}.py")
    help_text = description or name.replace("_", " ").capitalize()
    args = [json.dumps(name), json.dumps(help_text)]
    if label_list:
        args.append("[" + ", ".join(f'"{label}"' for label in label_list) + "]")
    if not text:
        text = f'"""Custom Prometheus metrics ({module}): import them where they are measured."""\n'
    text = add_import(text, f"from metrics.registry import {type_.value}")
    text = text.rstrip("\n") + f"\n\n{constant} = {type_.value}({', '.join(args)})\n"
    written = write_edit(ctx, path, text, dry_run=dry_run, what=f"{constant} {type_.value}")
    usage = (
        f"{constant}.labels(...).inc()"
        if label_list and type_ == MetricType.counter
        else f"{constant}.inc()"
        if type_ == MetricType.counter
        else f"{constant}.observe(seconds)"
    )
    _done(
        ctx,
        [written],
        f"`from metrics.{module} import {constant}`, then {usage}; it appears on /metrics",
        dry_run=dry_run,
    )
