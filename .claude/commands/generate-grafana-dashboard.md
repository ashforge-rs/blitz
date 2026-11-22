Generate a Grafana dashboard JSON for the feature or domain described below.

Arguments: $ARGUMENTS

The argument describes what to visualise — e.g. `orders domain`, `auth error rates`,
`full application overview`.  If no argument is given, generate a complete application
overview dashboard equivalent to `grafana/dashboard.json`.

---

## Context to gather first

Before generating any JSON, read these files to understand what metrics exist:

1. **`src/metrics/registry.py`** — custom counters and histograms defined via the
   `counter()` / `histogram()` helper.  Note every metric `name` and its `labelnames`.

2. **`src/<domain>/domain.py`** (if a specific domain was requested) — look for any
   calls to `counter()` / `histogram()` inside the service or route handlers.

3. **`grafana/dashboard.json`** — the existing base dashboard; use it as a style
   reference (panel layout, field config conventions, variable templating).

4. **`src/app.py`** — confirm that `prometheus-fastapi-instrumentator` is wired in.
   The instrumentator emits two metric families by default:

   | Metric | Type | Labels |
   |---|---|---|
   | `http_requests_total` | Counter | `method`, `handler`, `status` |
   | `http_request_duration_seconds` | Histogram | `method`, `handler`, `le` |

---

## Output requirements

Produce a single, valid Grafana dashboard JSON object that:

### 1. Schema structure
- `"schemaVersion": 38` (Grafana 10+)
- Top-level `"__inputs"` array with one entry for the Prometheus datasource named
  `DS_PROMETHEUS`
- Top-level `"__requires"` array listing panel types used
- `"uid"` — short kebab-case identifier derived from the argument (e.g. `blitz-orders-001`)
- `"title"` — descriptive title (e.g. `blitz — Orders Domain`)
- `"tags": ["fastapi", "blitz", "<domain-slug>"]`
- `"refresh": "30s"`, time range `"from": "now-1h"`, `"to": "now"`

### 2. Template variables
Always include a `$job` variable:
```json
{
  "name": "job",
  "type": "query",
  "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
  "definition": "label_values(http_requests_total, job)",
  "query": { "query": "label_values(http_requests_total, job)", "refId": "StandardVariableQuery" },
  "refresh": 2,
  "includeAll": true,
  "multi": false,
  "sort": 1
}
```
Add additional variables for any extra label dimensions the metrics expose
(e.g. `$handler`, `$status_class`).

### 3. Required row / panel structure

Organise panels into rows.  Always include:

**Row: Overview (stat panels, h=4 each, y=1)**
- Error Rate (5xx) — `percentunit`, red threshold at 0.05
- P99 Latency (ms) — `ms`, red threshold at 500
- P50 Latency (ms) — `ms`, yellow threshold at 200
- Requests / sec — `reqps`

**Row: Traffic (timeseries, h=8)**
- Request Rate by Status — `sum by (status)(rate(http_requests_total{job=~"$job"}[$__rate_interval]))`
- Request Rate by Handler — `sum by (handler)(rate(...))`

**Row: Latency (timeseries, h=8)**
- Latency Percentiles (p50 / p90 / p99) — all on one panel, unit `s`
- P99 Latency by Handler

**Row: Errors (timeseries, h=8)**
- 5xx rate by handler (fixed red colour)
- 4xx rate by handler (fixed orange colour)

**Row: Top Routes (table, h=8)**
- Columns: handler, method, req/s, p99 latency, error rate
- Sort descending by req/s
- Use `instant: true` targets

**Domain-specific rows** (only if a specific domain was requested):
For each custom metric found in the domain, add an appropriate panel:
- Counter → timeseries of `rate(...[$__rate_interval])` broken down by all label dimensions
- Histogram → p50/p90/p99 timeseries + a separate "requests/sec" timeseries

### 4. Panel conventions
- All `datasource` fields: `{ "type": "prometheus", "uid": "${DS_PROMETHEUS}" }`
- Use `$__rate_interval` (not a fixed `5m`) in all `rate()` / `histogram_quantile()` calls
- Panel IDs: sequential integers starting at 1; row panels get even tens (10, 20, 30…)
- Grid layout: 24-column grid, stat panels 4-wide, timeseries 12-wide, tables 24-wide
- Legend: `{ "calcs": ["mean", "max", "lastNotNull"], "displayMode": "table", "placement": "bottom" }`
- Tooltip: `{ "mode": "multi", "sort": "desc" }`
- `fillOpacity: 10` for regular timeseries, `20` for error timeseries
- Units: `reqps` for rate, `s` for raw duration, `ms` for stat panels, `percentunit` for ratios

### 5. Output format
- Write the JSON to `grafana/<slug>.json` (e.g. `grafana/orders.json`)
- If the argument is empty or "overview", overwrite `grafana/dashboard.json`
- Pretty-print with 2-space indentation
- Do **not** include any prose — output the JSON file only

---

## After generating

1. Validate the JSON parses: `python3 -c "import json, sys; json.load(open('grafana/<slug>.json'))"`
2. Mention how to import into Grafana:
   - Grafana UI → **Dashboards → Import → Upload JSON file** → select the generated file
   - Or provision it via `grafana/provisioning/dashboards/` (see Grafana docs)
