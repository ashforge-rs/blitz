"""Template sets: directories of ``*.tmpl`` files rendered with ``string.Template``.

A set lives in ``<templates dir>/<set>/`` and mirrors the project layout. Both file paths
and contents use ``$placeholders`` (``$$`` for a literal ``$``); the ``.tmpl`` suffix is
dropped on render. ``template.toml`` may hold:

- ``description``: one line for ``blitz template list``;
- ``extends``: another set whose files this one inherits (and may replace);
- ``exclude``: inherited files to drop, as output paths (``tests/domains/$name/fuzz/test_fuzz.py``).

Several template directories can be searched: the built-in one first, then a project's own
(``[tool.blitz] templates``). A later directory replaces files of the same set file by file,
and can add new sets.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
SUFFIX = ".tmpl"
MANIFEST = "template.toml"


class TemplateError(Exception):
    """A template set is missing or malformed, or a placeholder has no value."""


@dataclass(frozen=True, slots=True)
class RenderedFile:
    path: Path  # relative to the project root
    content: str


@dataclass(frozen=True, slots=True)
class TemplateSet:
    name: str
    description: str
    #: Output path pattern (``src/domains/$name/models.py``) → template file on disk.
    files: dict[str, Path] = field(default_factory=dict)
    #: Directories the set was assembled from, built-in first.
    layers: tuple[Path, ...] = ()

    def sources(self) -> list[str]:
        return sorted(self.files)

    def placeholders(self) -> set[str]:
        names: set[str] = set()
        for pattern, source in self.files.items():
            for text in (pattern, source.read_text()):
                names.update(Template(text).get_identifiers())
        return names

    def render(self, values: dict[str, str]) -> list[RenderedFile]:
        rendered = []
        for pattern in self.sources():
            source = self.files[pattern]
            try:
                path = Template(pattern).substitute(values)
                content = Template(source.read_text()).substitute(values)
            except KeyError as exc:
                raise TemplateError(f"{self.name}/{pattern}: no value for ${exc.args[0]}") from exc
            except ValueError as exc:  # a lone `$`: should have been `$$`
                raise TemplateError(f"{self.name}/{pattern}: {exc}") from exc
            rendered.append(RenderedFile(Path(path), content))
        return rendered


def _manifest(directory: Path) -> dict[str, object]:
    path = directory / MANIFEST
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise TemplateError(f"{path}: {exc}") from exc


def _names(search: list[Path]) -> list[str]:
    names = {p.name for d in search if d.is_dir() for p in d.iterdir() if p.is_dir()}
    return sorted(names)


def load(name: str, search: list[Path] | None = None, _seen: tuple[str, ...] = ()) -> TemplateSet:
    search = search or [TEMPLATES_DIR]
    if name in _seen:
        raise TemplateError(f"template set {name!r} extends itself ({' → '.join((*_seen, name))})")
    layers = [d / name for d in search if (d / name).is_dir()]
    if not layers:
        raise TemplateError(
            f"unknown template set {name!r} (available: {', '.join(_names(search))})"
        )

    files: dict[str, Path] = {}
    description = ""
    all_layers: tuple[Path, ...] = ()
    for layer in layers:
        meta = _manifest(layer)
        if parent := meta.get("extends"):
            base = load(str(parent), search, (*_seen, name))
            files |= base.files
            description = description or base.description
            all_layers += base.layers
        for excluded in meta.get("exclude", []):  # type: ignore[attr-defined]
            files.pop(str(excluded), None)
        for source in sorted(layer.rglob(f"*{SUFFIX}")):
            files[str(source.relative_to(layer)).removesuffix(SUFFIX)] = source
        description = str(meta.get("description", description))
        all_layers += (layer,)
    return TemplateSet(name, description, files, all_layers)


def available(search: list[Path] | None = None) -> list[TemplateSet]:
    search = search or [TEMPLATES_DIR]
    return [load(name, search) for name in _names(search)]
