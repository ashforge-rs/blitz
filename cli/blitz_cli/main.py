"""``blitz`` — generate code from the predefined templates and manage the project's boilerplate."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from . import fields as fields_mod
from . import naming
from .project import Project, ProjectError, find_root, tidy
from .templates import TemplateError, available, load

if TYPE_CHECKING:
    from collections.abc import Callable

app = typer.Typer(
    help="Generate code from blitz's templates and manage domains and services.",
    no_args_is_help=True,
    add_completion=False,
)
domain_app = typer.Typer(
    help="Domains: business features under src/domains/.", no_args_is_help=True
)
service_app = typer.Typer(help="Services: ASGI apps under src/services/.", no_args_is_help=True)
template_app = typer.Typer(help="The predefined template sets.", no_args_is_help=True)
app.add_typer(domain_app, name="domain")
app.add_typer(service_app, name="service")
app.add_typer(template_app, name="template")

DryRun = Annotated[bool, typer.Option("--dry-run", help="Show what would change; write nothing.")]
Yes = Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")]


def _fail(message: str) -> typer.Exit:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def _warn(message: str) -> None:
    typer.secho(f"warning: {message}", fg=typer.colors.YELLOW, err=True)


@app.callback()
def _root(
    ctx: typer.Context,
    root: Annotated[
        Path | None,
        typer.Option(help="Project root (default: nearest parent with src/services/)."),
    ] = None,
) -> None:
    ctx.obj = root


def _project(ctx: typer.Context) -> Project:
    root: Path | None = ctx.find_root().obj
    try:
        return Project(root.resolve() if root else find_root(Path.cwd()))
    except ProjectError as exc:
        raise _fail(str(exc)) from exc


def _generate(
    project: Project, set_name: str, values: dict[str, str], *, dry_run: bool
) -> list[Path]:
    """Render a template set into the project; refuse to overwrite any file."""
    try:
        files = load(set_name).render(values)
    except TemplateError as exc:
        raise _fail(str(exc)) from exc
    existing = [f.path for f in files if (project.root / f.path).exists()]
    if existing:
        raise _fail(f"{existing[0]} already exists; nothing written")
    written = []
    for file in files:
        target = project.root / file.path
        typer.echo(f"  {'would create' if dry_run else 'created'} {file.path}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content)
            written.append(target)
    return written


# ── domain ───────────────────────────────────────────────────────────────────


FieldsOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--field",
        "-f",
        help="Entity field as name:type, `?` for optional (title:str, notes:str?). Repeatable. "
        f"Types: {', '.join(fields_mod.TYPES)}.",
        show_default="name:str",
    ),
]


def _parse_fields(specs: list[str] | None) -> list[fields_mod.EntityField]:
    if not specs:
        return list(fields_mod.DEFAULT_FIELDS)
    try:
        parsed = [fields_mod.parse(spec) for spec in specs]
        fields_mod.check_fields(parsed)
    except fields_mod.FieldError as exc:
        raise _fail(str(exc)) from exc
    return parsed


def _create_domain(
    project: Project,
    name: str,
    entity: str,
    service: str,
    entity_fields: list[fields_mod.EntityField],
    *,
    register: bool,
    dry_run: bool,
) -> None:
    error = naming.check_name(name, "domain") or naming.check_entity(entity)
    if error:
        raise _fail(error)
    if (project.domains_dir / name).exists():
        raise _fail(f"src/domains/{name} already exists")
    if register and not project.registry(service).exists():
        raise _fail(f"service {service!r} not found (src/services/{service}/domains.py)")

    values = naming.domain_values(name, entity, service, entity_fields)
    written = _generate(project, "domain", values, dry_run=dry_run)
    if register:
        if dry_run:
            typer.echo(f"  would register in src/services/{service}/domains.py")
        else:
            project.register(service, name)
            written.append(project.registry(service))
            typer.echo(f"  registered in src/services/{service}/domains.py")
    if dry_run:
        return
    if warning := tidy(project.root, written):
        _warn(warning)
    typer.echo(f"\nNext: customise, then `make verify`; routes are served at /v1/{values['route']}")


@domain_app.command("new")
def domain_new(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="snake_case package name, e.g. orders.")],
    entity: Annotated[
        str | None,
        typer.Option(help="PascalCase entity class.", show_default="singular of NAME"),
    ] = None,
    field: FieldsOpt = None,
    service: Annotated[str, typer.Option(help="Service to register the domain with.")] = "api",
    register: Annotated[
        bool, typer.Option("--register/--no-register", help="Add it to the service's DOMAINS.")
    ] = True,
    dry_run: DryRun = False,
) -> None:
    """Scaffold a domain package and its tests from the `domain` template, and register it."""
    project = _project(ctx)
    entity = entity or naming.default_entity(name)
    _create_domain(
        project, name, entity, service, _parse_fields(field), register=register, dry_run=dry_run
    )


# ── crud (entity-first, with a wizard) ───────────────────────────────────────


def _ask(text: str, check: Callable[[str], str | None], default: str | None = None) -> str:
    """Prompt until ``check`` accepts the answer (it returns an error message or None)."""
    while True:
        answer = str(typer.prompt(text, default=default)).strip()
        error = check(answer)
        if error is None:
            return answer
        typer.secho(f"  {error}", fg=typer.colors.RED, err=True)


def _ask_fields() -> list[fields_mod.EntityField]:
    typer.echo(f"Fields (blank name to finish). Types: {', '.join(fields_mod.TYPES)}")
    collected: list[fields_mod.EntityField] = []

    def check_name(answer: str) -> str | None:
        if not answer:
            return None if collected else "add at least one field"
        if any(f.name == answer for f in collected):
            return f"{answer!r} is already a field"
        return fields_mod.check_field_name(answer)

    def check_type(answer: str) -> str | None:
        return None if answer in fields_mod.TYPES else f"use one of {', '.join(fields_mod.TYPES)}"

    while name := _ask("  Field name", check_name, default=""):
        type_ = _ask("  Type", check_type, default="str")
        required = typer.confirm("  Required?", default=True)
        collected.append(fields_mod.EntityField(name, type_, required))
    return collected


@app.command("crud")
def crud(
    ctx: typer.Context,
    entity: Annotated[
        str | None,
        typer.Argument(help="PascalCase entity, e.g. Product. Omit it to run the wizard."),
    ] = None,
    field: FieldsOpt = None,
    domain: Annotated[
        str | None, typer.Option(help="Domain package.", show_default="plural of ENTITY")
    ] = None,
    service: Annotated[str, typer.Option(help="Service to register the domain with.")] = "api",
    dry_run: DryRun = False,
) -> None:
    """Generate an entity and its CRUD API (a new domain). Asks for whatever is not given.

    The questions are kept basic: name, fields, types, required. Add validation,
    defaults and business rules to the generated code afterwards.
    """
    project = _project(ctx)
    wizard = entity is None
    if entity is None:
        entity = _ask("Entity name (PascalCase, e.g. Product)", naming.check_entity)
    elif error := naming.check_entity(entity):
        raise _fail(error)
    if domain is None:
        default = naming.plural(naming.snake(entity))
        domain = (
            _ask("Domain package", lambda a: naming.check_name(a, "domain"), default=default)
            if wizard
            else default
        )
    services = project.services()
    if wizard and len(services) > 1:
        service = _ask(
            "Service", lambda a: None if a in services else f"one of {services}", default=service
        )
    entity_fields = _parse_fields(field) if field else _ask_fields()

    if field is None:  # anything was asked: confirm before writing
        specs = ", ".join(f.spec for f in entity_fields)
        typer.echo(f"\n{entity} ({specs}) → src/domains/{domain}/, served by {service}")
        if not typer.confirm("Generate?", default=True):
            raise typer.Abort
    _create_domain(project, domain, entity, service, entity_fields, register=True, dry_run=dry_run)


@domain_app.command("list")
def domain_list(ctx: typer.Context) -> None:
    """List domains, the services that serve them, and whether they have tests."""
    project = _project(ctx)
    domains = project.domains()
    if not domains:
        typer.echo("no domains")
        return
    width = max(len(d) for d in domains)
    for domain in domains:
        services = ", ".join(project.services_serving(domain)) or "(not registered)"
        tests = "tests" if (project.root / "tests" / "domains" / domain).is_dir() else "no tests"
        typer.echo(f"{domain:<{width}}  {services}  [{tests}]")


@domain_app.command("remove")
def domain_remove(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Domain package to delete.")],
    yes: Yes = False,
) -> None:
    """Delete a domain package and its tests, and unregister it from every service."""
    project = _project(ctx)
    targets = [project.domains_dir / name, project.root / "tests" / "domains" / name]
    services = project.services_serving(name)
    if not any(t.exists() for t in targets) and not services:
        raise _fail(f"no domain {name!r}")
    typer.echo(
        f"This deletes {', '.join(project.rel(t) for t in targets if t.exists()) or 'no files'}"
    )
    if services:
        typer.echo(f"and unregisters it from: {', '.join(services)}")
    if not yes:
        typer.confirm("Continue?", abort=True)
    for target in targets:
        if project.remove_tree(target):
            typer.echo(f"  deleted {project.rel(target)}")
    for service in services:
        project.unregister(service, name)
        typer.echo(f"  unregistered from src/services/{service}/domains.py")
    if warning := tidy(project.root, [project.registry(s) for s in services]):
        _warn(warning)


# ── service ──────────────────────────────────────────────────────────────────


@service_app.command("new")
def service_new(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="snake_case service name, e.g. worker.")],
    dry_run: DryRun = False,
) -> None:
    """Scaffold an ASGI service (main.py, domains.py, Dockerfile) from the `service` template."""
    project = _project(ctx)
    if error := naming.check_name(name, "service"):
        raise _fail(error)
    if (project.services_dir / name).exists():
        raise _fail(f"src/services/{name} already exists")
    written = _generate(project, "service", {"service": name}, dry_run=dry_run)
    if dry_run:
        return
    if warning := tidy(project.root, written):
        _warn(warning)
    typer.echo(
        f"\nNext: `make domain DOMAIN=<name> SERVICE={name}`, then `make dev SERVICE={name}`"
    )


@service_app.command("list")
def service_list(ctx: typer.Context) -> None:
    """List services and the domains each one serves."""
    project = _project(ctx)
    for service in project.services():
        typer.echo(f"{service}: {', '.join(project.registered(service)) or '(no domains)'}")


# ── template ─────────────────────────────────────────────────────────────────


@template_app.command("list")
def template_list() -> None:
    """List the template sets."""
    for template_set in available():
        typer.echo(f"{template_set.name}: {template_set.description}")


@template_app.command("show")
def template_show(name: Annotated[str, typer.Argument(help="Template set name.")]) -> None:
    """Show a template set's placeholders and the files it generates."""
    try:
        template_set = load(name)
    except TemplateError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(f"{template_set.name}: {template_set.description}")
    typer.echo(f"placeholders: {', '.join(sorted(template_set.placeholders()))}")
    for source in template_set.sources():
        typer.echo(f"  {str(source).removesuffix('.tmpl')}")


def main() -> None:
    app()
