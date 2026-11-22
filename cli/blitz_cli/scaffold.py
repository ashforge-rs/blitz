"""Turn the boilerplate into a project: which files a project gets and how they are renamed.

``blitz new`` renders the boilerplate at one commit with the user's answers; ``blitz update``
renders the commit the project started from and a newer one *the same way*, then merges
the difference into the project. That only works if rendering is deterministic, so every
transform here is a pure function of (path, text, answers, template identity).
"""

import io
import re
import subprocess
import tarfile
from dataclasses import asdict, dataclass, fields
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

#: Not copied into a new project: the template's own history and its example apps.
EXCLUDED = ("CHANGELOG.md",)
EXAMPLES_DIR = "examples/"
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
PYTHON_RE = re.compile(r"^3\.(1[0-9]|[2-9][0-9])$")


class ScaffoldError(Exception):
    """The template source cannot be read, or an answer is invalid."""


@dataclass(frozen=True, slots=True)
class Answers:
    name: str
    description: str = "FastAPI service"
    owner: str = ""
    python: str = ""  # "" keeps the template's version
    examples: bool = False

    def check(self) -> None:
        if not NAME_RE.match(self.name):
            raise ScaffoldError(f"invalid project name {self.name!r}: use kebab-case, e.g. my-api")
        if self.python and not PYTHON_RE.match(self.python):
            raise ScaffoldError(f"invalid Python version {self.python!r}: e.g. 3.15")
        if self.owner and not re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$", self.owner):
            raise ScaffoldError(f"invalid GitHub owner {self.owner!r}")
        if any(c in self.description for c in '"\\\n'):
            raise ScaffoldError("the description must be one line without quotes or backslashes")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Answers:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(frozen=True, slots=True)
class Identity:
    """The template's own name, owner and Python version, read from the tree being rendered."""

    name: str
    owner: str
    python: str

    @classmethod
    def of(cls, files: dict[str, bytes]) -> Identity:
        pyproject = files.get("pyproject.toml", b"").decode(errors="replace")
        name = _first(r'(?m)^name = "([^"]+)"', pyproject) or "blitz"
        python = _first(r'(?m)^requires-python = ">=([0-9.]+)"', pyproject) or ""
        variables = files.get("infra/variables.tf", b"").decode(errors="replace")
        owner = _first(r'variable "github_owner" \{[^}]*?default\s*=\s*"([^"]*)"', variables) or ""
        return cls(name, owner, python)


def _first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1) if match else None


# ── reading a template tree ──────────────────────────────────────────────────


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)  # noqa: S603, S607


def clone(source: str, into: Path) -> Path:
    """Clone ``source`` (a path or URL) into ``into`` without checking files out."""
    result = _git("clone", "--quiet", "--no-checkout", source, str(into))
    if result.returncode != 0:
        raise ScaffoldError(f"git clone {source}: {result.stderr.decode().strip() or 'failed'}")
    return into


def resolve(repo: Path, ref: str) -> str:
    result = _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=repo)
    if result.returncode != 0:
        raise ScaffoldError(f"no commit {ref!r} in the template repository")
    return result.stdout.decode().strip()


def tree(repo: Path, commit: str) -> dict[str, bytes]:
    """Every file of ``commit``, path → bytes."""
    result = _git("archive", "--format=tar", commit, cwd=repo)
    if result.returncode != 0:
        raise ScaffoldError(f"git archive {commit}: {result.stderr.decode().strip() or 'failed'}")
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
        for member in tar.getmembers():
            if member.isfile() and (handle := tar.extractfile(member)) is not None:
                files[member.name] = handle.read()
    return files


# ── rendering ────────────────────────────────────────────────────────────────


def included(path: str, answers: Answers) -> bool:
    if path in EXCLUDED:
        return False
    return answers.examples or not path.startswith(EXAMPLES_DIR)


def render(files: dict[str, bytes], answers: Answers) -> dict[str, bytes]:
    """The project ``answers`` describe, from one template tree."""
    identity = Identity.of(files)
    out: dict[str, bytes] = {}
    for path, data in files.items():
        if not included(path, answers):
            continue
        try:
            text = data.decode()
        except UnicodeDecodeError:
            out[path] = data  # binary: copied as is
            continue
        out[path] = transform(path, text, answers, identity).encode()
    return out


def _set(pattern: str, value: str, text: str, *, count: int = 0) -> str:
    """Replace group 2 of every match (group 1 and 3 are kept); ``value`` is literal."""
    return re.sub(
        pattern,
        lambda m: m.group(1) + value + (m.group(3) if m.re.groups >= 3 else ""),
        text,
        count=count,
        flags=re.MULTILINE | re.DOTALL,
    )


def transform(path: str, text: str, a: Answers, t: Identity) -> str:
    """Rename the template to the project, file by file. Unmatched patterns are no-ops."""
    old = re.escape(t.name)
    python = a.python or t.python
    if path == "pyproject.toml":
        text = _set(rf'^(name = ")({old})(")$', a.name, text, count=1)
        text = _set(r'^(version = ")([^"]*)(")$', "0.1.0", text, count=1)
        text = _set(r'^(description = ")([^"]*)(")$', a.description, text, count=1)
        if a.python:
            text = _set(r'^(requires-python = ">=)([0-9.]+)(")$', python, text, count=1)
            text = _set(r'^(target-version = "py)([0-9]+)(")$', python.replace(".", ""), text)
            text = _set(r'^(python_version = ")([0-9.]+)(")$', python, text)
    elif path == "uv.lock":
        text = _set(rf'^(\[\[package\]\]\nname = ")({old})("\nversion = ")', a.name, text, count=1)
        text = _set(
            rf'^(\[\[package\]\]\nname = "{re.escape(a.name)}"\nversion = ")'
            r'([^"]*)("\nsource = \{ editable = "\." \})',
            "0.1.0",
            text,
            count=1,
        )
        if a.python:
            text = _set(r'^(requires-python = ">=)([0-9.]+)(")$', python, text, count=1)
    elif path == ".release-please-manifest.json":
        text = _set(r'("\."\s*:\s*")([^"]*)(")', "0.1.0", text)
    elif path == "src/config.py":
        for setting in ("OPENAPI_TITLE", "OTEL_SERVICE_NAME"):
            text = _set(rf'^(\s*{setting}: str = ")({old})(")$', a.name, text)
    elif path == ".env.example":
        text = _set(rf"^(OPENAPI_TITLE=)({old})()$", a.name, text)
        text = _set(rf"^(# OTEL_SERVICE_NAME=)({old})()$", a.name, text)
    elif path == "README.md":
        text = _set(rf"^(# )({old})(\b)", a.name, text, count=1)
    elif path.startswith("src/services/") and path.endswith("/Dockerfile"):
        text = _set(rf'(image\.title=")({old})(-)', a.name, text)
        if a.python:
            text = _set(r"^(FROM python:)([0-9.]+)(-slim)", python, text)
    elif path == "infra/variables.tf":
        text = _set(r'(variable "repository_name" \{[^}]*?default\s*=\s*")([^"]*)(")', a.name, text)
        if a.owner:
            text = _set(
                r'(variable "github_owner" \{[^}]*?default\s*=\s*")([^"]*)(")', a.owner, text
            )
    elif path == "infra/terraform.tfvars.example":
        text = _set(r'^(repository_name\s*=\s*")([^"]*)(")', a.name, text)
        if a.owner:
            text = _set(r'^(github_owner\s*=\s*")([^"]*)(")', a.owner, text)
    elif path == "infra/repository.tf":
        text = _set(r'^(\s*description\s*=\s*")([^"]*)(")', a.description, text, count=1)
    elif path == ".github/CODEOWNERS" and a.owner and t.owner:
        text = text.replace(f"@{t.owner}", f"@{a.owner}")
    elif path.startswith(".github/workflows/"):
        if a.python:
            text = _set(r'^(\s*PYTHON_PRIMARY:\s*"?)([0-9.]+)("?)', python, text)
        if not a.examples:  # the example-* jobs build examples/, which is not copied
            text = re.sub(
                r"^  # ─+\n  # example-[\w-]+ —.*?(?=^  # ─+\n  # (?!example-))",
                "",
                text,
                flags=re.MULTILINE | re.DOTALL,
            )
    elif path == "Makefile" and not a.examples:
        text = re.sub(r"^\t\$\(MAKE\) -C examples/\S+ verify\n", "", text, flags=re.MULTILINE)
        text = text.replace("(+ examples/, cli/)", "(+ cli/)")
    elif path == "AGENTS.md" and not a.examples:
        text = re.sub(
            r"the reference implementations are\n`examples/todo/` \(full\) and `examples/consent/` \(lean\)\.",
            lambda _: (
                "the reference implementations\n(todo: full, consent: lean) are in the boilerplate's examples directory."
            ),
            text,
        )
    return text


def project_files(root: Path, paths: set[str]) -> dict[str, bytes]:
    """The project's current content of ``paths`` (absent files are left out)."""
    found = {}
    for path in paths:
        target = root / path
        if target.is_file():
            found[path] = target.read_bytes()
    return found


# ── the record of where a project came from ([tool.blitz.template]) ──────────

RECORD_HEADER = "[tool.blitz.template]"


@dataclass(frozen=True, slots=True)
class Record:
    source: str  # git URL or path the template is cloned from
    commit: str  # the template commit the project matches
    answers: Answers


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def record_block(record: Record) -> str:
    lines = [
        RECORD_HEADER,
        "# Written by `blitz new`; `blitz update` merges template changes since `commit`.",
        f"source = {_toml(record.source)}",
        f"commit = {_toml(record.commit)}",
        *(f"{key} = {_toml(value)}" for key, value in record.answers.to_dict().items()),
    ]
    return "\n".join(lines) + "\n"


def write_record(pyproject: Path, record: Record) -> None:
    """Add or replace the ``[tool.blitz.template]`` table (the rest of the file is kept)."""
    text = pyproject.read_text()
    block = record_block(record)
    match = re.search(rf"(?ms)^{re.escape(RECORD_HEADER)}\n.*?(?=^\[|\Z)", text)
    if match:
        text = (
            text[: match.start()]
            + block
            + ("\n" if match.end() < len(text) else "")
            + text[match.end() :]
        )
    else:
        text = text.rstrip("\n") + "\n\n" + block
    pyproject.write_text(text)


def read_record(pyproject: Path) -> Record | None:
    import tomllib

    try:
        table = (
            tomllib.loads(pyproject.read_text()).get("tool", {}).get("blitz", {}).get("template")
        )
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ScaffoldError(f"{pyproject}: {exc}") from exc
    if not isinstance(table, dict):
        return None
    try:
        return Record(str(table["source"]), str(table["commit"]), Answers.from_dict(table))
    except (KeyError, TypeError) as exc:
        raise ScaffoldError(f"[tool.blitz.template] is incomplete: {exc}") from exc
