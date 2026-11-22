"""Entity fields: ``title:str`` / ``notes:str?`` specs → snippets for the ``domain`` templates."""

import keyword
import re
from dataclasses import dataclass

_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
#: Set by the generated model itself.
RESERVED_FIELDS = frozenset({"id", "created_by", "updated_by", "created_at", "updated_at"})


@dataclass(frozen=True, slots=True)
class FieldType:
    annotation: str
    #: Two distinct JSON values: the created one and the updated one.
    samples: tuple[object, object]
    strategy: str  # Hypothesis strategy producing valid JSON-compatible input
    constraints: str = ""  # extra pydantic Field(...) arguments


TYPES: dict[str, FieldType] = {
    "str": FieldType(
        "str", ("a", "b"), "st.text(min_size=1, max_size=255)", "min_length=1, max_length=255"
    ),
    "int": FieldType("int", (1, 2), "st.integers()"),
    "float": FieldType("float", (1.5, 2.5), "st.floats(allow_nan=False, allow_infinity=False)"),
    "bool": FieldType("bool", (True, False), "st.booleans()"),
    "date": FieldType("date", ("2024-01-01", "2024-01-02"), "st.dates().map(str)"),
    "datetime": FieldType(
        "datetime",
        ("2024-01-01T00:00:00", "2024-01-02T00:00:00"),
        "st.datetimes().map(datetime.isoformat)",
    ),
    "uuid": FieldType(
        "UUID",
        ("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"),
        "st.uuids().map(str)",
    ),
}


class FieldError(ValueError):
    """A field spec or field list is invalid."""


@dataclass(frozen=True, slots=True)
class EntityField:
    name: str
    type: str
    required: bool = True

    @property
    def spec(self) -> str:
        return f"{self.name}:{self.type}{'' if self.required else '?'}"

    @property
    def _type(self) -> FieldType:
        return TYPES[self.type]

    def model_line(self) -> str:
        ann = self._type.annotation
        return f"{self.name}: {ann}" if self.required else f"{self.name}: {ann} | None = None"

    def create_line(self) -> str:
        ann, constraints = self._type.annotation, self._type.constraints
        if self.required:
            return (
                f"{self.name}: {ann} = Field({constraints})"
                if constraints
                else f"{self.name}: {ann}"
            )
        if self.type == "str":
            return f"{self.name}: {ann} | None = Field(default=None, max_length=255)"
        return f"{self.name}: {ann} | None = None"

    def update_line(self) -> str:
        ann, constraints = self._type.annotation, self._type.constraints
        if self.type == "str" and not self.required:
            constraints = "max_length=255"
        if not constraints:
            return f"{self.name}: {ann} | None = None"
        return f"{self.name}: {ann} | None = Field(default=None, {constraints})"

    def strategy(self) -> str:
        base = self._type.strategy
        return base if self.required else f"st.none() | {base}"


def check_field_name(name: str) -> str | None:
    if not _FIELD_RE.match(name):
        return f"invalid field name {name!r}: use snake_case, e.g. unit_price"
    if name in RESERVED_FIELDS or name.startswith("model_") or keyword.iskeyword(name):
        return f"field name {name!r} is reserved"
    return None


def parse(spec: str) -> EntityField:
    """``title:str`` (required) or ``notes:str?`` (optional); the type defaults to ``str``."""
    name, _, type_ = spec.strip().partition(":")
    type_ = type_ or "str"
    required = not type_.endswith("?")
    type_ = type_.removesuffix("?")
    if error := check_field_name(name):
        raise FieldError(error)
    if type_ not in TYPES:
        raise FieldError(f"unknown type {type_!r} for {name!r}: use one of {', '.join(TYPES)}")
    return EntityField(name, type_, required)


def check_fields(fields: list[EntityField]) -> None:
    if not fields:
        raise FieldError("an entity needs at least one field")
    seen: set[str] = set()
    for field in fields:
        if field.name in seen:
            raise FieldError(f"field {field.name!r} is declared twice")
        seen.add(field.name)


DEFAULT_FIELDS = [EntityField("name", "str")]


def template_values(fields: list[EntityField]) -> dict[str, str]:
    """Placeholder values the ``domain`` templates use for the entity's fields."""
    check_fields(fields)
    types = {f.type for f in fields}
    dt_names = sorted({"UTC", "datetime"} | ({"date"} & types))
    imports = f"from datetime import {', '.join(dt_names)}\n"
    if "uuid" in types:
        imports += (
            "from uuid import UUID  # noqa: TC003 — pydantic resolves field types at runtime\n"
        )

    first = fields[0]
    first_create, first_update = TYPES[first.type].samples
    sample = {f.name: TYPES[f.type].samples[0] for f in fields}
    strategies = ", ".join(f'"{f.name}": {f.strategy()}' for f in fields)
    fuzz_imports = "from datetime import datetime\n" if "datetime" in types else ""

    def block(lines: list[str]) -> str:
        return "\n".join(f"    {line}" for line in lines)

    return {
        "model_imports": imports,
        "model_fields": block([f.model_line() for f in fields]),
        "create_fields": block([f.create_line() for f in fields]),
        "update_fields": block([f.update_line() for f in fields]),
        "sample": repr(sample),
        "first_field": first.name,
        "first_create": repr(first_create),
        "first_update": repr(first_update),
        "sample_update": repr({first.name: first_update}),
        "invalid_body": repr({first.name: []}),
        "fuzz_imports": fuzz_imports,
        "fuzz_strategy": f"st.fixed_dictionaries({{{strategies}}})",
    }
