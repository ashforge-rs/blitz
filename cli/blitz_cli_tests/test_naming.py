import pytest

from blitz_cli import naming


@pytest.mark.parametrize(
    ("name", "entity"),
    [
        ("orders", "Order"),
        ("user_profiles", "UserProfile"),
        ("categories", "Category"),
        ("billing", "Billing"),
        ("address", "Address"),
    ],
)
def test_default_entity(name, entity):
    assert naming.default_entity(name) == entity


@pytest.mark.parametrize("bad", ["Orders", "1orders", "order-items", "example", ""])
def test_check_name_rejects(bad):
    assert naming.check_name(bad, "domain") is not None


@pytest.mark.parametrize("bad", ["order", "Order-Item", "1Order"])
def test_check_entity_rejects(bad):
    assert naming.check_entity(bad) is not None


def test_domain_values():
    values = naming.domain_values("user_profiles", "UserProfile", "worker")
    assert (
        values.items()
        >= {
            "name": "user_profiles",
            "service": "worker",
            "route": "user-profiles",
            "Plural": "UserProfiles",
            "Entity": "UserProfile",
            "entity": "user_profile",
            "entity_words": "user profile",
        }.items()
    )


@pytest.mark.parametrize(
    ("singular", "plural"),
    [("product", "products"), ("category", "categories"), ("box", "boxes"), ("day", "days")],
)
def test_plural(singular, plural):
    assert naming.plural(singular) == plural
