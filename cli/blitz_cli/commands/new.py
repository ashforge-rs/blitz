"""``blitz new``: start a project from the boilerplate, renamed and recorded for ``blitz update``."""

import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from blitz_cli.scaffold import (
    Answers,
    Record,
    ScaffoldError,
    clone,
    render,
    resolve,
    tree,
    write_record,
)

from .common import fail

#: The boilerplate this CLI ships in (cli/blitz_cli/commands/ → repository root).
HOME_TEMPLATE = Path(__file__).resolve().parents[3]


def default_source() -> str:
    """The boilerplate's `origin` URL when it has one (so `update` works anywhere), else its path."""
    if not (HOME_TEMPLATE / ".git").exists():
        raise fail("this CLI is not inside a git checkout of the boilerplate; pass --from")
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(HOME_TEMPLATE), "remote", "get-url", "origin"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    url = result.stdout.strip()
    return url if result.returncode == 0 and url else str(HOME_TEMPLATE)


def _git(directory: Path, *args: str) -> bool:
    result = subprocess.run(["git", "-C", str(directory), *args], capture_output=True, check=False)  # noqa: S603, S607
    return result.returncode == 0


def new(
    directory: Annotated[
        Path, typer.Argument(help="Where to create the project (must not exist or be empty).")
    ],
    name: Annotated[
        str | None,
        typer.Option(help="kebab-case project name.", show_default="the directory name"),
    ] = None,
    description: Annotated[str, typer.Option(help="One-line description.")] = "FastAPI service",
    owner: Annotated[
        str, typer.Option(help="GitHub owner (user or org): infra/, CODEOWNERS.")
    ] = "",
    python: Annotated[
        str, typer.Option(help="Minimum Python version, e.g. 3.15.", show_default="the template's")
    ] = "",
    examples: Annotated[
        bool, typer.Option("--examples/--no-examples", help="Copy examples/ too.")
    ] = False,
    source: Annotated[
        str | None,
        typer.Option(
            "--from",
            help="Template: a git URL or path.",
            show_default="the boilerplate this CLI belongs to (its origin URL)",
        ),
    ] = None,
    ref: Annotated[str, typer.Option(help="Template branch, tag or commit.")] = "HEAD",
    git_init: Annotated[
        bool, typer.Option("--git/--no-git", help="git init and commit the new project.")
    ] = True,
) -> None:
    """Create a project from the boilerplate: renamed, configured, and recorded for updates.

    Copies the template at one commit (never uncommitted changes), renames it
    (package, lock, OPENAPI_TITLE, OTEL_SERVICE_NAME, Dockerfile labels, infra/,
    CODEOWNERS, README title), resets the version to 0.1.0, and drops CHANGELOG.md
    and examples/. [tool.blitz.template] in pyproject.toml records the source,
    commit and these answers, which `blitz update` uses to merge later template
    changes. The example domain stays: AGENTS.md and the tests use it as the
    reference (`blitz domain remove example` once you have your own).
    """
    target = directory.resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise fail(f"{directory} exists and is not empty")
    answers = Answers(
        name=name or target.name,
        description=description,
        owner=owner,
        python=python,
        examples=examples,
    )
    origin = source or default_source()
    try:
        answers.check()
        with tempfile.TemporaryDirectory(prefix="blitz-new-") as tmp:
            repo = clone(origin, Path(tmp) / "template")
            commit = resolve(repo, ref)
            files = render(tree(repo, commit), answers)
    except ScaffoldError as exc:
        raise fail(str(exc)) from exc

    for path, data in sorted(files.items()):
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    write_record(target / "pyproject.toml", Record(origin, commit, answers))
    typer.echo(f"created {directory} ({len(files)} files) from {origin} @ {commit[:12]}")

    if git_init:
        committed = (
            _git(target, "-c", "init.defaultBranch=main", "init", "--quiet")
            and _git(target, "add", "--all")
            and _git(
                target,
                "commit",
                "--quiet",
                "-m",
                f"chore: start from the blitz template ({commit[:12]})",
            )
        )
        if not committed:
            typer.secho(
                "warning: git init/commit did not complete (is user.name/email set?); commit yourself",
                fg=typer.colors.YELLOW,
                err=True,
            )
    steps = [f"cd {directory}", "uv lock" if python else "", "uv sync", "make verify"]
    typer.echo("\nNext: " + " && ".join(s for s in steps if s))
