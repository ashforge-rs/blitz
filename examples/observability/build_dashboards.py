"""Build the examples' Grafana dashboards from blitz's base dashboard plus their own panels.

    python3 examples/observability/build_dashboards.py

Writes ``examples/todo/grafana/todo-dashboard.json`` and
``examples/consent/grafana/consent-dashboard.json``.  Standard library only.

Datasources are dashboard variables (``${prometheus}``, ``${postgres}``), not import
inputs, so the files work both provisioned (``make up`` here) and imported by hand.
SQL panels use portable SQL only: the examples' tests run every query on SQLite.
"""

import copy
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = json.loads((REPO / "grafana" / "dashboard.json").read_text())

PROM = {"type": "prometheus", "uid": "${prometheus}"}
PG = {"type": "grafana-postgresql-datasource", "uid": "${postgres}"}
RATE = "$__rate_interval"
Panel = dict[str, Any]


class Layout:
    """Hands out panel ids and grid positions row by row (24 columns)."""

    def __init__(self, first_id: int, y: int) -> None:
        self.next_id, self.y, self.x, self.h = first_id, y, 0, 0

    def row(self, title: str, row_id: int) -> Panel:
        self._newline()
        panel = {"id": row_id, "type": "row", "title": title, "collapsed": False,
                 "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []}
        self.y += 1
        self.next_id = row_id + 1
        return panel

    def place(self, panel: Panel, w: int, h: int) -> Panel:
        if self.x + w > 24:
            self._newline()
        panel["id"] = self.next_id
        panel["gridPos"] = {"h": h, "w": w, "x": self.x, "y": self.y}
        self.next_id += 1
        self.x += w
        self.h = max(self.h, h)
        return panel

    def _newline(self) -> None:
        self.y += self.h
        self.x, self.h = 0, 0


def _prom(expr: str, legend: str = "", *, instant: bool = False, fmt: str = "time_series") -> dict[str, Any]:
    return {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": "A",
            "instant": instant, "range": not instant, "format": fmt}


def stat(title: str, expr: str, *, unit: str = "short", description: str = "",
         steps: list[dict[str, Any]] | None = None) -> Panel:
    return {
        "type": "stat", "title": title, "description": description, "datasource": PROM,
        "targets": [_prom(expr, title)],
        "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "thresholds"}, "mappings": [],
                                     "thresholds": {"mode": "absolute", "steps": steps or [{"color": "blue", "value": None}]}},
                        "overrides": []},
        "options": {"colorMode": "background", "graphMode": "area", "justifyMode": "center", "textMode": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "orientation": "auto"},
    }


def timeseries(title: str, targets: list[tuple[str, str]], *, unit: str = "short",
               stacked: bool = False, description: str = "", color: str | None = None) -> Panel:
    return {
        "type": "timeseries", "title": title, "description": description, "datasource": PROM,
        "targets": [_prom(e, l) | {"refId": chr(65 + i)} for i, (e, l) in enumerate(targets)],
        "fieldConfig": {"defaults": {"unit": unit,
                                     "color": {"mode": "fixed", "fixedColor": color} if color else {"mode": "palette-classic"},
                                     "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 20 if stacked or color else 10,
                                                "showPoints": "never", "spanNulls": False,
                                                "stacking": {"group": "A", "mode": "normal" if stacked else "none"}}},
                        "overrides": []},
        "options": {"legend": {"calcs": ["lastNotNull", "max"], "displayMode": "table", "placement": "bottom"},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def bargauge(title: str, expr: str, legend: str, *, description: str = "", unit: str = "short") -> Panel:
    return {
        "type": "bargauge", "title": title, "description": description, "datasource": PROM,
        "targets": [_prom(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": unit, "min": 0, "color": {"mode": "continuous-GrYlRd"}}, "overrides": []},
        "options": {"displayMode": "gradient", "orientation": "horizontal", "showUnfilled": True,
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    }


def piechart(title: str, expr: str, legend: str, *, description: str = "") -> Panel:
    return {
        "type": "piechart", "title": title, "description": description, "datasource": PROM,
        "targets": [_prom(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": "short", "color": {"mode": "palette-classic"}}, "overrides": []},
        "options": {"pieType": "donut", "legend": {"displayMode": "table", "placement": "right", "values": ["value", "percent"]},
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "tooltip": {"mode": "single"}},
    }


def sql_table(title: str, sql: str, *, description: str = "") -> Panel:
    return {
        "type": "table", "title": title, "description": description, "datasource": PG,
        "targets": [{"datasource": PG, "editorMode": "code", "format": "table", "rawQuery": True,
                     "rawSql": " ".join(sql.split()), "refId": "A"}],
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "filterable": True}}, "overrides": []},
        "options": {"showHeader": True, "footer": {"show": False}},
    }


def _retarget(panel: Panel) -> Panel:
    """A base-dashboard panel, pointed at the ``${prometheus}`` variable."""
    text = json.dumps(panel).replace("${DS_PROMETHEUS}", "${prometheus}")
    return json.loads(text)


def _variables(postgres_name: str) -> list[dict[str, Any]]:
    job = _retarget(copy.deepcopy(BASE["templating"]["list"][0]))
    datasource = {"type": "datasource", "hide": 0, "current": {}, "options": [], "refresh": 1,
                  "includeAll": False, "multi": False}
    return [
        datasource | {"name": "prometheus", "label": "Prometheus", "query": "prometheus", "regex": ""},
        datasource | {"name": "postgres", "label": "Database", "query": "grafana-postgresql-datasource",
                      "regex": f"/{postgres_name}/"},
        job,
    ]


def _http_rows() -> list[Panel]:
    """blitz's request panels: overview stats, traffic, latency, errors (ids 1-32)."""
    keep = {1, 2, 3, 4, 5, 10, 11, 12, 20, 21, 22, 30, 31, 32}
    return [_retarget(copy.deepcopy(p)) for p in BASE["panels"] if p["id"] in keep]


def _dashboard(uid: str, title: str, description: str, tags: list[str], postgres: str,
               panels: list[Panel]) -> dict[str, Any]:
    return {
        "__requires": [{"type": "panel", "id": t, "name": t} for t in ("stat", "timeseries", "bargauge", "piechart", "table")]
        + [{"type": "datasource", "id": "prometheus", "name": "Prometheus"},
           {"type": "datasource", "id": "grafana-postgresql-datasource", "name": "PostgreSQL"}],
        "annotations": BASE["annotations"], "description": description, "editable": True,
        "fiscalYearStartMonth": 0, "graphTooltip": 1, "id": None, "links": [], "panels": panels,
        "refresh": "30s", "schemaVersion": 38, "tags": ["blitz", "example", *tags],
        "templating": {"list": _variables(postgres)}, "time": {"from": "now-6h", "to": "now"},
        "timepicker": {}, "timezone": "browser", "title": title, "uid": uid, "version": 1,
    }


def todo_dashboard() -> dict[str, Any]:
    J = 'job=~"$job"'
    L = Layout(first_id=0, y=33)
    panels = _http_rows()
    panels += [
        L.row("Data (from the database)", 40),
        L.place(stat("Registered users", f"sum(todoapp_registered_users{{{J}}})"), 5, 4),
        L.place(stat("Active API tokens", f"sum(todoapp_active_api_tokens{{{J}}})"), 5, 4),
        L.place(stat("Open todos", f'sum(todoapp_todos{{{J}, done="false"}})'), 5, 4),
        L.place(stat("Done todos", f'sum(todoapp_todos{{{J}, done="true"}})'), 4, 4),
        L.place(stat("Users with todos", f"sum(todoapp_users_with_todos{{{J}}})"), 5, 4),
        L.place(sql_table("Latest todos", """
            SELECT created_at AS created, title, done, owner_id AS owner
            FROM todos ORDER BY created_at DESC LIMIT 50""",
            description="The newest todos. Owners are user ids: the todos context stores no names."), 14, 9),
        L.place(sql_table("Users", """
            SELECT u.created_at AS registered, u.name, u.id,
                   (SELECT count(*) FROM api_tokens t WHERE t.user_id = u.id) AS tokens
            FROM users u ORDER BY u.created_at""",
            description="Email addresses are deliberately not shown: dashboards are not for personal data."), 10, 9),
        L.row("Activity", 50),
        L.place(timeseries("Registrations by outcome", [(f"sum by (result) (rate(todoapp_users_registered_total{{{J}}}[{RATE}]))", "{{result}}")], unit="ops", stacked=True), 12, 8),
        L.place(timeseries("Todos created by outcome", [(f"sum by (result) (rate(todoapp_todos_created_total{{{J}}}[{RATE}]))", "{{result}}")], unit="ops", stacked=True), 12, 8),
        L.place(timeseries("Authentication attempts", [(f"sum by (result) (rate(todoapp_auth_attempts_total{{{J}}}[{RATE}]))", "{{result}}")], unit="ops", stacked=True), 12, 8),
        L.place(timeseries("Users storage failures", [(f"sum by (operation) (rate(todoapp_users_storage_failures_total{{{J}}}[{RATE}]))", "{{operation}}")], unit="ops", color="red"), 12, 8),
        L.row("Audit outbox", 60),
        L.place(timeseries("Oldest undelivered entry", [(f"max by (outbox) (todoapp_audit_outbox_oldest_age_seconds{{{J}}})", "{{outbox}}")], unit="s",
                           description="Alert AuditOutboxStale fires above 300 s for 5 minutes."), 8, 8),
        L.place(timeseries("Pending entries", [(f"sum by (outbox) (todoapp_audit_outbox_pending{{{J}}})", "{{outbox}}")]), 8, 8),
        L.place(timeseries("Delivery failures", [(f"sum by (outbox) (rate(todoapp_audit_delivery_failures_total{{{J}}}[{RATE}]))", "{{outbox}}")], unit="ops", color="red"), 8, 8),
    ]
    return _dashboard("blitz-todo-001", "blitz — Todo app",
                      "examples/todo: requests, the stored users and todos, activity and audit delivery.",
                      ["todo-app"], "Todo", panels)


def consent_dashboard() -> dict[str, Any]:
    J = 'job=~"$job"'
    L = Layout(first_id=0, y=33)
    panels = _http_rows()
    panels += [
        L.row("Consent today (from the ledger, judged by the profile)", 40),
        L.place(stat("Known subjects", f"sum(consentapp_known_subjects{{{J}}})"), 6, 4),
        L.place(stat("Processing allowed (subject × purpose)", f"sum(consentapp_subjects_may_process{{{J}}})",
                     description="Pairs where GetConsentStatus would answer may_process = true."), 6, 4),
        L.place(stat("Renewal required", f'sum(consentapp_subjects{{{J}, state="renewal_required"}})',
                     description="Granted under a notice that has since changed: ask these subjects again.",
                     steps=[{"color": "green", "value": None}, {"color": "orange", "value": 1}]), 6, 4),
        L.place(stat("Withdrawn", f'sum(consentapp_subjects{{{J}, state="withdrawn"}})'), 6, 4),
        L.place(timeseries("Subjects by state, per purpose",
                           [(f"sum by (purpose, state) (consentapp_subjects{{{J}}})", "{{purpose}} · {{state}}")],
                           description="Every known subject's current state for each purpose."), 12, 9),
        L.place(bargauge("Processing allowed, by purpose", f"sum by (purpose) (consentapp_subjects_may_process{{{J}}})", "{{purpose}}"), 12, 9),
        L.row("Ledger", 50),
        L.place(piechart("Grants by method", f'sum by (method) (consentapp_ledger_events{{{J}, decision="granted"}})', "{{method}}",
                         description="How subjects expressed consent. The GDPR profile accepts affirmative methods only."), 8, 8),
        L.place(piechart("Decisions by channel", f"sum by (source) (consentapp_ledger_events{{{J}}})", "{{source}}"), 8, 8),
        L.place(piechart("Grants vs withdrawals", f"sum by (decision) (consentapp_ledger_events{{{J}}})", "{{decision}}"), 8, 8),
        L.place(timeseries("Decisions recorded", [(f"sum by (decision) (rate(consentapp_decisions_total{{{J}}}[{RATE}]))", "{{decision}}")], unit="ops", stacked=True), 12, 8),
        L.place(timeseries("Refusals by reason", [(f"sum by (code) (rate(consentapp_refusals_total{{{J}}}[{RATE}]))", "{{code}}")], unit="ops", color="orange",
                           description="method_not_accepted is, for example, a pre-ticked box."), 12, 8),
        L.row("Records", 60),
        L.place(sql_table("Recent decisions", """
            SELECT recorded_at, subject_id, purpose, decision, method, notice_version, source, recorded_by, profile
            FROM consent_events ORDER BY seq DESC LIMIT 100""",
            description="The newest entries in the append-only ledger: the evidence of consent."), 24, 10),
        L.place(sql_table("Purposes and notices", """
            SELECT p.slug AS purpose, p.description, p.notice_version AS current_notice,
                   p.notice_published_at AS published,
                   (SELECT count(*) FROM purpose_notices n WHERE n.purpose = p.slug) AS notice_versions,
                   (SELECT count(*) FROM consent_events e WHERE e.purpose = p.slug) AS decisions
            FROM purposes p ORDER BY p.slug"""), 24, 7),
    ]
    return _dashboard("blitz-consent-001", "blitz — Consent app",
                      "examples/consent: requests, where every subject stands per purpose, the ledger and its records.",
                      ["consent-app", "gdpr"], "Consent", panels)


def main() -> None:
    for dashboard, target in ((todo_dashboard(), REPO / "examples/todo/grafana/todo-dashboard.json"),
                              (consent_dashboard(), REPO / "examples/consent/grafana/consent-dashboard.json")):
        ids = [p["id"] for p in dashboard["panels"]]
        assert len(ids) == len(set(ids)), f"duplicate panel ids in {target.name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(dashboard, indent=2) + "\n")
        print(f"{target.relative_to(REPO)}: {len(dashboard['panels'])} panels")


if __name__ == "__main__":
    main()
