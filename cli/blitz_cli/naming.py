"""Name validation and case conversion for generated code."""

import re
from typing import TYPE_CHECKING

from . import fields as fields_mod

if TYPE_CHECKING:
    from .fields import EntityField

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENTITY_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
#: Names that would shadow the reference implementation.
RESERVED = frozenset({"example"})


def pascal(snake_name: str) -> str:
    return "".join(part.capitalize() for part in snake_name.split("_"))


def snake(pascal_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", pascal_name).lower()


def default_entity(name: str) -> str:
    """``orders`` → ``Order``, ``user_profiles`` → ``UserProfile``, ``billing`` → ``Billing``."""
    base = pascal(name)
    if base.endswith("ies") and len(base) > 3:
        return base[:-3] + "y"
    if base.endswith("s") and not base.endswith("ss") and len(base) > 1:
        return base[:-1]
    return base


def check_name(name: str, kind: str) -> str | None:
    """Return why ``name`` is not a usable snake_case package name, or None."""
    if not NAME_RE.match(name):
        return f"invalid {kind} name {name!r}: use snake_case, e.g. orders"
    if name in RESERVED:
        return f"{kind} name {name!r} is reserved"
    return None


def check_entity(entity: str) -> str | None:
    if not ENTITY_RE.match(entity):
        return f"invalid entity {entity!r}: use PascalCase, e.g. Order"
    return None


def plural(snake_name: str) -> str:
    """``product`` → ``products``, ``category`` → ``categories``, ``box`` → ``boxes``."""
    if re.search(r"[^aeiou]y$", snake_name):
        return snake_name[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", snake_name):
        return snake_name + "es"
    return snake_name + "s"


def domain_values(
    name: str, entity: str, service: str = "api", fields: list[EntityField] | None = None
) -> dict[str, str]:
    """Placeholder values for the ``domain`` template set."""
    return fields_mod.template_values(fields or fields_mod.DEFAULT_FIELDS) | {
        "name": name,
        "service": service,
        "route": name.replace("_", "-"),
        "Plural": pascal(name),
        "Entity": entity,
        "entity": snake(entity),
        "entity_words": snake(entity).replace("_", " "),
    }
