import pytest

from todo_app.todos.entities import Title
from todo_app.users.entities import DisplayName, EmailAddress


def test_email_is_trimmed_and_lower_cased() -> None:
    assert EmailAddress("  Ada@Example.COM ").value == "ada@example.com"


def test_emails_differing_only_in_case_are_equal() -> None:
    assert EmailAddress("ADA@example.com") == EmailAddress("ada@example.com")


@pytest.mark.parametrize(
    "raw", ["", "ada", "ada@", "@example.com", "ada@example", "a da@example.com"]
)
def test_invalid_email_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="not a valid email address"):
        EmailAddress(raw)


def test_overlong_email_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a valid email address"):
        EmailAddress("a" * 250 + "@example.com")


def test_invalid_email_message_does_not_echo_the_value() -> None:
    with pytest.raises(ValueError, match="not a valid email address") as exc:
        EmailAddress("secret-person")
    assert "secret-person" not in str(exc.value)


@pytest.mark.parametrize("cls", [DisplayName, Title])
def test_text_values_are_trimmed(cls: type[DisplayName] | type[Title]) -> None:
    assert cls("  Buy milk  ").value == "Buy milk"


@pytest.mark.parametrize(("cls", "limit"), [(DisplayName, 100), (Title, 200)])
def test_text_values_enforce_length(cls: type[DisplayName] | type[Title], limit: int) -> None:
    assert cls("x" * limit).value == "x" * limit
    for bad in ["", "   ", "x" * (limit + 1)]:
        with pytest.raises(ValueError, match="characters"):
            cls(bad)


def test_value_objects_are_immutable() -> None:
    title = Title("Buy milk")
    with pytest.raises(AttributeError):
        title.value = "Sell milk"  # type: ignore[misc]  # asserting the frozen dataclass
