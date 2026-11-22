from pathlib import Path

import pytest

from blitz_cli import naming, templates


def test_builtin_sets_have_descriptions():
    sets = {t.name: t for t in templates.available()}
    assert {"domain", "service"} <= sets.keys()
    assert all(t.description for t in sets.values())


@pytest.mark.parametrize(
    ("set_name", "values"),
    [
        ("domain", naming.domain_values("orders", "Order")),
        ("service", {"service": "worker"}),
    ],
)
def test_values_cover_every_placeholder(set_name, values):
    template_set = templates.load(set_name)
    assert template_set.placeholders() == values.keys()
    for file in template_set.render(values):
        assert "$" not in str(file.path)
        assert not file.path.name.endswith(".tmpl")


def test_dollar_escape_survives(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "$x.txt.tmpl").write_text("ENV PATH=$$PATH $x\n")
    [file] = templates.load("demo", [tmp_path]).render({"x": "hi"})
    assert file == templates.RenderedFile(Path("hi.txt"), "ENV PATH=$PATH hi\n")


def test_missing_value_names_placeholder():
    with pytest.raises(templates.TemplateError, match=r"\$Entity"):
        templates.load("domain").render({"name": "orders"})


def test_unknown_set():
    with pytest.raises(templates.TemplateError, match="available: "):
        templates.load("nope")
