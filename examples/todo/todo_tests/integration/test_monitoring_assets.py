"""The Grafana dashboard and alert rules only query metrics the app really exports."""

import json
import re
from pathlib import Path

import pytest
from prometheus_client import REGISTRY

import todo_app.factory
import todo_app.todos.adapters.sql_reporting
import todo_app.users.adapters.sql_reporting  # noqa: F401
from todo_app.cli import composition  # noqa: F401 — and the CLI side, for completeness

GRAFANA = Path(__file__).resolve().parents[2] / "grafana"
METRIC = re.compile(r"\btodoapp_[a-z_]+")


def _exported() -> set[str]:
    names = set()
    for family in REGISTRY.collect():
        names.add(family.name)
        names.update(sample.name for sample in family.samples)
    # Counters are exported as <name>_total; a labelled one has no sample until first use.
    names.update(
        f"{family.name}_total" for family in REGISTRY.collect() if family.type == "counter"
    )
    return names


def _referenced(text: str) -> set[str]:
    return set(METRIC.findall(text))


@pytest.mark.parametrize("asset", ["todo-dashboard.json", "alerts.yml"])
def test_every_referenced_metric_exists(asset: str) -> None:
    text = (GRAFANA / asset).read_text()
    if asset.endswith(".json"):
        json.loads(text)  # and the dashboard is valid JSON

    missing = sorted(_referenced(text) - _exported())

    assert _referenced(text), f"{asset} references no todoapp_* metric"
    assert missing == [], f"{asset} queries metrics the app doesn't export"
