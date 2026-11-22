"""``blitz update``: merge template changes since the project was made (or last updated).

Three versions of every file meet:

- base: the template at the recorded commit, rendered with the project's answers;
- theirs: the template at the new commit, rendered the same way;
- ours: the project as it is now.

A file the project never touched takes the template's new version; one the template
did not change stays as it is; one both changed is merged line by line (``git
merge-file``) and, where both changed the same lines, gets conflict markers to resolve.
"""

import subprocess
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from blitz_cli.scaffold import (
    Record,
    ScaffoldError,
    clone,
    project_files,
    read_record,
    render,
    resolve,
    tree,
    write_record,
)

from .common import fail, project


class Outcome(StrEnum):
    added = "added"
    updated = "updated"
    merged = "merged"
    removed = "removed"
    conflict = "CONFLICT"
    kept = "kept"


@dataclass(frozen=True, slots=True)
class Step:
    path: str
    outcome: Outcome
    note: str = ""
    content: bytes | None = None  # what to write; None with `removed` deletes


def _merge(ours: bytes, base: bytes, theirs: bytes) -> tuple[bytes, bool]:
    """Three-way merge; returns (result, clean)."""
    with tempfile.TemporaryDirectory(prefix="blitz-merge-") as tmp:
        paths = []
        for label, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(tmp) / label
            path.write_bytes(data)
            paths.append(str(path))
        result = subprocess.run(  # noqa: S603
            ["git", "merge-file", "-p", "-L", "project", "-L", "base", "-L", "template", *paths],  # noqa: S607
            capture_output=True,
            check=False,
        )
    if result.returncode < 0 or result.returncode > 127:
        raise ScaffoldError(f"git merge-file failed: {result.stderr.decode().strip()}")
    return result.stdout, result.returncode == 0


def plan(base: dict[str, bytes], theirs: dict[str, bytes], ours: dict[str, bytes]) -> list[Step]:
    steps = []
    for path in sorted(base.keys() | theirs.keys()):
        b, t, o = base.get(path), theirs.get(path), ours.get(path)
        if b == t or o == t:
            continue  # the template did not change it, or the project already matches
        if t is None:  # removed from the template
            if o is None:
                continue
            if o == b:
                steps.append(Step(path, Outcome.removed))
            else:
                steps.append(Step(path, Outcome.kept, "removed from the template but changed here"))
        elif o is None:
            if b is None:
                steps.append(Step(path, Outcome.added, content=t))
            else:
                steps.append(Step(path, Outcome.kept, "deleted here; the template changed it"))
        elif o == b:
            steps.append(Step(path, Outcome.updated, content=t))
        else:
            merged, clean = _merge(o, b or b"", t)
            if clean:
                steps.append(Step(path, Outcome.merged, content=merged))
            else:
                steps.append(
                    Step(path, Outcome.conflict, "both changed the same lines", content=merged)
                )
    return steps


def _clean_worktree(root: Path) -> bool:
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "status", "--porcelain"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and not result.stdout.strip()


def update(
    ctx: typer.Context,
    to: Annotated[str, typer.Option(help="Template branch, tag or commit to update to.")] = "HEAD",
    source: Annotated[
        str | None,
        typer.Option(
            "--from", help="Template source, if it moved.", show_default="the recorded source"
        ),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the plan; write nothing.")
    ] = False,
    allow_dirty: Annotated[
        bool, typer.Option(help="Run with uncommitted changes (they get mixed into the result).")
    ] = False,
) -> None:
    """Merge template changes made since the project's recorded commit.

    Needs [tool.blitz.template] (written by `blitz new`) and, unless --allow-dirty, a
    clean git tree, so `git diff` shows exactly what the update changed and `git
    checkout .` undoes it. Files the project changed are merged; overlapping edits
    get conflict markers (<<<<<<< project / >>>>>>> template) and exit status 1.
    """
    proj = project(ctx)
    pyproject = proj.root / "pyproject.toml"
    try:
        record = read_record(pyproject)
    except ScaffoldError as exc:
        raise fail(str(exc)) from exc
    if record is None:
        raise fail(
            "no [tool.blitz.template] in pyproject.toml (made by `blitz new`); "
            "nothing to update from"
        )
    if not dry_run and not allow_dirty and not _clean_worktree(proj.root):
        raise fail("uncommitted changes: commit or stash them first (or pass --allow-dirty)")
    origin = source or record.source

    try:
        with tempfile.TemporaryDirectory(prefix="blitz-update-") as tmp:
            repo = clone(origin, Path(tmp) / "template")
            new_commit = resolve(repo, to)
            if new_commit == record.commit:
                typer.echo(f"up to date with {origin} @ {new_commit[:12]}")
                return
            base = render(tree(repo, record.commit), record.answers)
            theirs = render(tree(repo, new_commit), record.answers)
        ours = project_files(proj.root, base.keys() | theirs.keys())
        steps = plan(base, theirs, ours)
    except ScaffoldError as exc:
        raise fail(str(exc)) from exc

    for step in steps:
        note = f"  ({step.note})" if step.note else ""
        label = (
            typer.style(step.outcome.value, fg=typer.colors.RED, bold=True)
            if step.outcome == Outcome.conflict
            else step.outcome.value
        )
        typer.echo(f"  {label:<10} {step.path}{note}")
        if dry_run:
            continue
        target = proj.root / step.path
        if step.outcome == Outcome.removed:
            target.unlink(missing_ok=True)
        elif step.content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(step.content)

    conflicts = [s for s in steps if s.outcome == Outcome.conflict]
    summary = f"{record.commit[:12]} → {new_commit[:12]}: {len(steps)} files"
    if dry_run:
        typer.echo(f"\nwould update {summary}")
        return
    write_record(pyproject, Record(origin, new_commit, record.answers))
    typer.echo(
        f"\nupdated {summary}; review with `git diff`, then `uv lock && uv sync` and `make verify`"
    )
    if conflicts:
        typer.secho(
            f"{len(conflicts)} conflicts: resolve the <<<<<<< markers in "
            + ", ".join(s.path for s in conflicts),
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
