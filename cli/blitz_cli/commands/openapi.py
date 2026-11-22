"""``blitz openapi``: export a service's OpenAPI schema and flag breaking changes."""

import io
import json
from dataclasses import asdict
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer

from blitz_cli.openapi_diff import diff
from blitz_cli.runner import APP_FOR_SERVICE, RunnerError, run_json

from .common import complete_services, fail, project, service_or_default

_SCRIPT = (
    APP_FOR_SERVICE + "\nimport json, sys\nprint(json.dumps(app_for(sys.argv[1]).openapi()))\n"
)


def export_schema(root: Path, service: str, src: Path | None = None) -> dict[str, Any]:
    try:
        schema: dict[str, Any] = run_json(root, _SCRIPT, service, src=src)
    except RunnerError as exc:
        raise fail(f"could not build the {service} app: {exc}") from exc
    return schema


def _schema_at(root: Path, ref: str, service: str) -> dict[str, Any]:
    """The schema the service had at git ``ref`` (its src/ run in today's venv)."""
    archive = subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "archive", "--format=tar", ref, "src"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise fail(f"git archive {ref}: {archive.stderr.decode().strip() or 'failed'}")
    with tempfile.TemporaryDirectory(prefix="blitz-openapi-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        if not (Path(tmp) / "src" / "services" / service).is_dir():
            raise fail(f"service {service!r} does not exist at {ref}")
        return export_schema(root, service, src=Path(tmp) / "src")


def openapi(
    ctx: typer.Context,
    service: Annotated[
        str | None,
        typer.Option(help="Service whose schema to export.", autocompletion=complete_services),
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Write the schema here (default: stdout).")
    ] = None,
    diff_ref: Annotated[
        str | None,
        typer.Option("--diff", help="Compare with the schema at this git ref (e.g. origin/main)."),
    ] = None,
    against: Annotated[
        Path | None, typer.Option(help="Compare with a saved schema file instead of a git ref.")
    ] = None,
    check: Annotated[
        bool, typer.Option("--check", help="Exit 1 when a change is breaking (for CI).")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the changes as JSON.")] = False,
) -> None:
    """Export the OpenAPI schema, or compare it with an earlier one and flag breaking changes.

    The schema comes from the real app (the service's DOMAINS included). --diff REF builds
    the app as it was at REF, using today's dependencies; --against compares with a
    committed openapi.json. Breaking: removed operations, responses or parameters,
    newly required inputs, narrower request types, removed or loosened response fields.
    """
    proj = project(ctx)
    service = service_or_default(ctx, service)
    if service not in proj.services():
        raise fail(f"unknown service {service!r} (have: {', '.join(proj.services())})")
    if diff_ref and against:
        raise fail("use --diff or --against, not both")
    current = export_schema(proj.root, service)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(current, indent=2) + "\n")
        typer.echo(
            f"wrote {out} ({len(current.get('paths', {}))} paths)", err=bool(diff_ref or against)
        )
    if not (diff_ref or against):
        if out is None:
            typer.echo(json.dumps(current, indent=2))
        return

    if against is not None:
        try:
            baseline = json.loads(against.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise fail(f"{against}: {exc}") from exc
        label = str(against)
    else:
        baseline = _schema_at(proj.root, str(diff_ref), service)
        label = str(diff_ref)

    changes = diff(baseline, current)
    breaking = [c for c in changes if c.breaking]
    if as_json:
        typer.echo(json.dumps([asdict(c) for c in changes], indent=2))
    else:
        for change in sorted(changes, key=lambda c: (not c.breaking, c.operation, c.message)):
            tag = (
                typer.style("BREAKING", fg=typer.colors.RED, bold=True)
                if change.breaking
                else "changed "
            )
            typer.echo(f"{tag}  {change.operation or '-'}  {change.message}")
        typer.echo(
            f"\n{service} vs {label}: {len(breaking)} breaking, {len(changes) - len(breaking)} other changes"
        )
    if check and breaking:
        raise typer.Exit(code=1)
