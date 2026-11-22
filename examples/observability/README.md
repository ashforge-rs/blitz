# Observability for the examples

Postgres, Prometheus and Grafana for [`examples/todo`](../todo) and
[`examples/consent`](../consent), with both dashboards provisioned.

```bash
make up          # Postgres :55432 (not 5432, so it can't clash with a local Postgres) · Prometheus :9090 · Grafana :3000 (admin/admin; anonymous viewing on)
make seed        # both apps' demo data, into Postgres
make todo        # terminal 1: the todo app on :8000
make consent     # terminal 2: the consent app on :8001
```

Open <http://localhost:3000>: the **Todo app** and **Consent app** folders hold the dashboards.
Metrics appear within about 15 seconds, once Prometheus has scraped the apps and the apps have
counted their data.

## What the dashboards show

Each dashboard has three kinds of panel:

| Kind | Source | Example |
| --- | --- | --- |
| Requests (rate, latency, errors) | Prometheus: blitz's HTTP metrics | p99 latency by route |
| The stored data, aggregated | Prometheus: business gauges each app recomputes from its database every `*_METRICS_REFRESH_SECONDS` (15 s) | consent state per purpose; open todos |
| The stored data, row by row | Postgres: SQL table panels | recent consent decisions; latest todos |

The business gauges are computed by the apps, not by the dashboards:
- **Consent:** states are derived by the `SummariseConsent` use case under the regulation
  profile, so the dashboard shows exactly what the API would answer.
- **Todo:** a small read-side adapter in each context counts its own tables.

Either way, data written by any process, `make seed` included, appears once an app is running.
The dashboards show no email addresses.

## Changing a dashboard

The JSON files are generated: edit [`build_dashboards.py`](build_dashboards.py), then run
`make dashboards`. Both examples' tests check that every queried metric exists and that every SQL
panel runs against the schema and returns the seeded data.

Datasources are dashboard variables (`${prometheus}`, and `${postgres}` matched by datasource
name), so the files work here and when imported by hand into another Grafana.

## Postgres for the examples' tests

The stack also creates `todo_test` and `consent_test`:

```bash
cd ../todo && TODO_TEST_POSTGRES_URL=postgresql+asyncpg://examples:examples@localhost:55432/todo_test make verify
cd ../consent && CONSENT_TEST_POSTGRES_URL=postgresql+asyncpg://examples:examples@localhost:55432/consent_test make verify
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `make up`: port already allocated | Something else uses 9090 or 3000. Postgres is published on **55432**, not 5432, so a locally installed Postgres can't clash. |
| `make seed`: `storage_unavailable` … `password authentication failed for user "examples"` | The seed reached a different Postgres, such as one on a host port forwarded into WSL. Check the URL uses port **55432**. |
| `make seed`: `storage_unavailable` … `could not reach the database` | The stack isn't running: `make up`. |
| `make seed`: `already_present` lists the demo users | They were seeded more than 24 hours ago, outside the replay window, so their tokens can't be reissued. `make reset`, then `make up` and `make seed`, starts fresh. |
| Dashboards empty; Prometheus targets (<http://localhost:9090/targets>) are `down` | The apps aren't running, or listen only on 127.0.0.1, which Prometheus can't reach from its container. `make todo` and `make consent` listen on all interfaces. |
| Some panels say "No data" | They count events since the app started, such as 5xx errors, decisions or failures. They fill in once those events happen. Business metrics refresh every 15 s. |
