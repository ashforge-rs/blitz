import pytest

from blitz_cli import fields
from blitz_cli.fields import EntityField


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("title:str", EntityField("title", "str")),
        ("title", EntityField("title", "str")),
        ("notes:str?", EntityField("notes", "str", required=False)),
        ("sku:uuid", EntityField("sku", "uuid")),
    ],
)
def test_parse(spec, expected):
    assert fields.parse(spec) == expected


@pytest.mark.parametrize(
    ("spec", "error"),
    [
        ("Title:str", "snake_case"),
        ("id:str", "reserved"),
        ("model_name:str", "reserved"),
        ("class:str", "reserved"),
        ("price:money", "unknown type"),
    ],
)
def test_parse_rejects(spec, error):
    with pytest.raises(fields.FieldError, match=error):
        fields.parse(spec)


def test_check_fields():
    with pytest.raises(fields.FieldError, match="at least one"):
        fields.check_fields([])
    with pytest.raises(fields.FieldError, match="twice"):
        fields.check_fields([EntityField("a", "str"), EntityField("a", "int")])


def test_lines():
    title = EntityField("title", "str")
    notes = EntityField("notes", "str", required=False)
    qty = EntityField("qty", "int", required=False)
    assert title.model_line() == "title: str"
    assert title.create_line() == "title: str = Field(min_length=1, max_length=255)"
    assert title.update_line() == (
        "title: str | None = Field(default=None, min_length=1, max_length=255)"
    )
    assert notes.model_line() == "notes: str | None = None"
    assert notes.create_line() == "notes: str | None = Field(default=None, max_length=255)"
    assert qty.create_line() == "qty: int | None = None"
    assert qty.update_line() == "qty: int | None = None"
    assert qty.strategy() == "st.none() | st.integers()"


def test_template_values_imports_only_what_is_used():
    plain = fields.template_values([EntityField("name", "str")])
    assert plain["model_imports"] == "from datetime import UTC, datetime\n"
    assert plain["fuzz_imports"] == ""

    rich = fields.template_values(
        [EntityField("on", "date"), EntityField("at", "datetime"), EntityField("ref", "uuid")]
    )
    assert rich["model_imports"].startswith("from datetime import UTC, date, datetime\n")
    assert "from uuid import UUID" in rich["model_imports"]
    assert rich["fuzz_imports"] == "from datetime import datetime\n"


def test_template_values_samples_use_first_field():
    values = fields.template_values([EntityField("price", "float"), EntityField("name", "str")])
    assert values["sample"] == "{'price': 1.5, 'name': 'a'}"
    assert values["sample_update"] == "{'price': 2.5}"
    assert values["first_create"] == "1.5"
    assert values["invalid_body"] == "{'price': []}"
