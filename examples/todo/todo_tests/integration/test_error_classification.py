"""Which driver errors count as "storage unavailable" (an outage) rather than a bug."""

import pytest
from sqlalchemy.exc import DBAPIError

from todo_app.persistence.errors import is_unavailable


class _DriverError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"SQLSTATE {sqlstate}")
        self.sqlstate = sqlstate


def _postgres_error(sqlstate: str) -> DBAPIError:
    return DBAPIError("SELECT 1", {}, _DriverError(sqlstate))


@pytest.mark.parametrize(
    "sqlstate",
    ["08006", "53300", "57P01", "40001", "40P01", "57014", "28P01", "28000", "3D000"],
    ids=[
        "connection",
        "too-many-connections",
        "shutdown",
        "serialization",
        "deadlock",
        "statement-timeout",
        "bad-password",
        "bad-role",
        "missing-database",
    ],
)
def test_outages_and_misconfiguration_are_unavailable(sqlstate: str) -> None:
    assert is_unavailable(_postgres_error(sqlstate))


@pytest.mark.parametrize(
    "sqlstate",
    ["42601", "42P01", "23505", "22001"],
    ids=["syntax", "no-table", "unique", "too-long"],
)
def test_bugs_and_constraint_violations_are_not(sqlstate: str) -> None:
    assert not is_unavailable(_postgres_error(sqlstate))
