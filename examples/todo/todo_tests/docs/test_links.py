"""The example's documentation only links to files, and headings, that exist."""

import re
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[2]
DOCS = [EXAMPLE / "README.md", *sorted((EXAMPLE / "docs").glob("*.md"))]
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6} (.+)$", re.MULTILINE)


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower-case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[`*_]", "", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _anchors(doc: Path) -> set[str]:
    return {_slug(h) for h in HEADING.findall(doc.read_text())}


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(EXAMPLE)))
def test_links_resolve(doc: Path) -> None:
    broken = []
    for link in LINK.findall(doc.read_text()):
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        path, _, anchor = link.partition("#")
        target = (doc.parent / path).resolve() if path else doc
        bad_anchor = bool(anchor) and target.suffix == ".md" and anchor not in _anchors(target)
        if not target.exists() or bad_anchor:
            broken.append(link)

    assert broken == [], f"{doc.name} has broken links"
