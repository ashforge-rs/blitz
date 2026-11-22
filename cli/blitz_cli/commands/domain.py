"""Domains: ``domain new|list|remove`` and the entity-first ``crud`` wizard."""

from typing import Annotated

import typer

from blitz_cli import fields as fields_mod
from blitz_cli import naming
from blitz_cli.project import ProjectError

from .common import (
    DryRun,
    ServiceOpt,
    Tests,
    Yes,
    ask,
    complete_domains,
    confirm,
    fail,
    finish,
    generate,
    project,
    service_or_default,
    state,
)

app = typer.Typer(help="Domains: business features under src/domains/.", no_args_is_help=True)

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
NoCrud = Annotated[
    bool,
    typer.Option(
        "--crud/--no-crud",
        help="Generate CRUD routes; --no-crud: entity, store and an empty router "
        "(add routes with `blitz g endpoint`).",
    ),
]
EntityOpt = Annotated[
    str | None,
    typer.Option(help="PascalCase entity class.", show_default="singular of NAME"),
]
Register = Annotated[
    bool, typer.Option("--register/--no-register", help="Add it to the service's DOMAINS.")
]


def parse_fields(specs: list[str] | None) -> list[fields_mod.EntityField]:
    if not specs:
        return list(fields_mod.DEFAULT_FIELDS)
    try:
        parsed = [fields_mod.parse(spec) for spec in specs]
        fields_mod.check_fields(parsed)
    except fields_mod.FieldError as exc:
        raise fail(str(exc)) from exc
    return parsed


def create_domain(
    ctx: typer.Context,
    name: str,
    entity: str,
    service: str,
    entity_fields: list[fields_mod.EntityField],
    *,
    register: bool,
    dry_run: bool,
    crud: bool = True,
    tests: bool | None = None,
) -> None:
    proj = project(ctx)
    error = naming.check_name(name, "domain") or naming.check_entity(entity)
    if error:
        raise fail(error)
    if (proj.domains_dir / name).exists():
        raise fail(f"src/domains/{name} already exists")
    if register and not proj.registry(service).exists():
        raise fail(f"service {service!r} not found (src/services/{service}/domains.py)")
    if register:
        try:  # before anything is written: a registry we cannot edit stops here
            proj.registration(service, name)
        except ProjectError as exc:
            raise fail(f"{exc}; nothing written") from exc

    values = naming.domain_values(name, entity, service, entity_fields)
    set_name = "domain" if crud else "domain-bare"
    written = generate(ctx, set_name, values, dry_run=dry_run, tests=tests)
    if register:
        if dry_run:
            typer.echo(f"  would register in src/services/{service}/domains.py")
        else:
            proj.register(service, name)
            written.append(proj.registry(service))
            typer.echo(f"  registered in src/services/{service}/domains.py")
    if dry_run:
        return
    route = values["route"]
    next_step = (
        f"customise, then `make verify`; routes are served at /v1/{route}"
        if crud
        else f"`blitz g endpoint {name} <name>` to add routes under /v1/{route}"
    )
    finish(ctx, written, next_step)


@app.command("new")
def domain_new(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="snake_case package name, e.g. orders.")],
    entity: EntityOpt = None,
    field: FieldsOpt = None,
    service: ServiceOpt = None,
    register: Register = True,
    crud: NoCrud = True,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """Scaffold a domain package and its tests, and register it with a service."""
    create_domain(
        ctx,
        name,
        entity or naming.default_entity(name),
        service_or_default(ctx, service),
        parse_fields(field),
        register=register,
        dry_run=dry_run,
        crud=crud,
        tests=tests,
    )


@app.command("list")
def domain_list(ctx: typer.Context) -> None:
    """List domains, the services that serve them, and whether they have tests."""
    proj = project(ctx)
    domains = proj.domains()
    if not domains:
        typer.echo("no domains")
        return
    width = max(len(d) for d in domains)
    for domain in domains:
        services = ", ".join(proj.services_serving(domain)) or "(not registered)"
        tests = "tests" if (proj.root / "tests" / "domains" / domain).is_dir() else "no tests"
        typer.echo(f"{domain:<{width}}  {services}  [{tests}]")


@app.command("remove")
def domain_remove(
    ctx: typer.Context,
    name: Annotated[
        str, typer.Argument(help="Domain package to delete.", autocompletion=complete_domains)
    ],
    yes: Yes = False,
) -> None:
    """Delete a domain package and its tests, and unregister it from every service."""
    proj = project(ctx)
    # Only a package name: `.`, `..` or a path would point rmtree at a parent directory.
    if not naming.NAME_RE.fullmatch(name):
        raise fail(f"invalid domain name {name!r}: a package under src/domains/, e.g. orders")
    targets = [proj.domains_dir / name, proj.root / "tests" / "domains" / name]
    services = proj.services_serving(name)
    if not any(t.exists() for t in targets) and not services:
        raise fail(f"no domain {name!r}")
    existing = ", ".join(proj.rel(t) for t in targets if t.exists()) or "no files"
    typer.echo(f"This deletes {existing}")
    if services:
        typer.echo(f"and unregisters it from: {', '.join(services)}")
    if not yes and not state(ctx).is_interactive:
        raise fail("deleting needs --yes in non-interactive mode")
    if not confirm(ctx, "Continue?", default=False, yes=yes):
        raise typer.Abort
    for target in targets:
        if proj.remove_tree(target):
            typer.echo(f"  deleted {proj.rel(target)}")
    for service in services:
        try:
            proj.unregister(service, name)
        except ProjectError as exc:
            raise fail(str(exc)) from exc
        typer.echo(f"  unregistered from src/services/{service}/domains.py")
    finish(ctx, [proj.registry(s) for s in services])


# ── crud (entity-first, with a wizard) ───────────────────────────────────────


def _ask_fields(ctx: typer.Context) -> list[fields_mod.EntityField]:
    if not state(ctx).is_interactive:
        return list(fields_mod.DEFAULT_FIELDS)
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

    while name := ask(ctx, "  Field name", check_name, default=""):
        type_ = ask(ctx, "  Type", check_type, default="str")
        required = typer.confirm("  Required?", default=True)
        collected.append(fields_mod.EntityField(name, type_, required))
    return collected


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
    service: ServiceOpt = None,
    tests: Tests = None,
    dry_run: DryRun = False,
) -> None:
    """Generate an entity and its CRUD API (a new domain). Asks for whatever is not given.

    The questions are kept basic: name, fields, types, required. Add validation,
    defaults and business rules to the generated code afterwards. Without a TTY,
    in CI or with --no-interactive nothing is asked: ENTITY is required and the
    fields default to name:str.
    """
    proj = project(ctx)
    wizard = entity is None
    if entity is None:
        entity = ask(
            ctx, "Entity name (PascalCase, e.g. Product)", naming.check_entity, flag="ENTITY"
        )
    elif error := naming.check_entity(entity):
        raise fail(error)
    if domain is None:
        default = naming.plural(naming.snake(entity))
        domain = (
            ask(ctx, "Domain package", lambda a: naming.check_name(a, "domain"), default=default)
            if wizard
            else default
        )
    service = service_or_default(ctx, service)
    services = proj.services()
    if wizard and len(services) > 1:
        service = ask(
            ctx,
            "Service",
            lambda a: None if a in services else f"one of {', '.join(services)}",
            default=service,
        )
    entity_fields = parse_fields(field) if field else _ask_fields(ctx)

    if field is None and state(ctx).is_interactive:  # something was asked: confirm it
        specs = ", ".join(f.spec for f in entity_fields)
        typer.echo(f"\n{entity} ({specs}) → src/domains/{domain}/, served by {service}")
        if not confirm(ctx, "Generate?"):
            raise typer.Abort
    create_domain(
        ctx, domain, entity, service, entity_fields, register=True, dry_run=dry_run, tests=tests
    )
