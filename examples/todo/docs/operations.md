# Operations

Running, configuring and monitoring `examples/todo`. Architecture is in
[architecture.md](architecture.md).

## Settings

Read from the environment or `.env` (see [`../.env.example`](../.env.example)). The
boilerplate's own settings (`PORT`, `ENVIRONMENT`, `RATE_LIMIT`, ...) still apply.

| Setting | Default | Meaning |
| --- | --- | --- |
| `TODO_DATABASE_URL` | `sqlite+aiosqlite:///todo.db` | SQLAlchemy URL; Postgres: `postgresql+asyncpg://user:password@host/db`. Secret. |
| `TODO_DB_MIGRATE_ON_STARTUP` | `true` | Migrate when the app or CLI starts. **Set `false` in production.** |
| `TODO_DB_CONNECT_TIMEOUT_SECONDS` | `5` | Postgres: wait for a new or pooled connection before failing. |
| `TODO_DB_BUSY_TIMEOUT_MS` | `5000` | SQLite: wait for another connection's write lock. |
| `TODO_OUTBOX_POLL_INTERVAL_SECONDS` | `0.5` | How often the relay delivers audit entries. |
| `TODO_OUTBOX_MAX_AGE_SECONDS` | `300` | `/health` returns 503 when an audit entry has waited longer. |
| `TODO_IDEMPOTENCY_PURGE_INTERVAL_SECONDS` | `3600` | How often expired idempotency records are purged. |

## Releasing a schema change

1. Add a revision: `uv run alembic -c todo_app/<context>/adapters/migrations/alembic.ini
   revision --autogenerate -m "..."`, then review it. `test_migrations.py` fails until the
   migrations and `sql_tables.py` agree.
2. Deploy with `TODO_DB_MIGRATE_ON_STARTUP=false`, and run `todo db upgrade` (or `make migrate`)
   as a release step before the new code starts. If you forget, startup refuses to run against
   a stale schema (`SchemaOutOfDateError`; CLI exit `78`).

## Monitoring

| Metric | Labels |
| --- | --- |
| `todoapp_users_registered_total` | `result`: `success`, `replayed`, `email_taken`, `idempotency_key_reused`, `error` |
| `todoapp_users_storage_failures_total` | `operation`: `users.register`, `users.authenticate` |
| `todoapp_todos_created_total` | `result`: `success`, `replayed`, `idempotency_key_reused`, `error` |
| `todoapp_auth_attempts_total` | `result`: `success`, `missing`, `invalid`, `error` |
| `todoapp_audit_outbox_pending` (gauge) | `outbox`: entries committed but not yet delivered |
| `todoapp_audit_outbox_oldest_age_seconds` (gauge) | `outbox`: age of the oldest undelivered entry |
| `todoapp_audit_delivered_total` / `_delivery_failures_total` | `outbox` |

- **`/health`** reports each context (`users`, `todos`): whether its database answers, how many
  audit entries are pending, and the age of the oldest. It returns **503** when a database is
  down or an entry has waited longer than `TODO_OUTBOX_MAX_AGE_SECONDS` (default 300 s), so a
  stuck relay takes the instance out of rotation instead of silently losing the audit trail's
  freshness.
- **Dashboard:** [`grafana/todo-dashboard.json`](../grafana/todo-dashboard.json). It has blitz's HTTP
  overview plus rows for users and auth, todos, and the audit outbox. Import it via Grafana →
  Dashboards → Import, or drop it into the repository's `grafana/provisioning/dashboards/`.
- **Alerts:** [`grafana/alerts.yml`](../grafana/alerts.yml), as Prometheus rules:

  | Alert | Fires when | Severity |
  | --- | --- | --- |
  | `AuditOutboxStale` | oldest audit entry is over 300 s old for 5 min | critical |
  | `AuditDeliveryFailing` | every delivery attempt fails for 10 min | warning |
  | `StorageUnavailable` | use cases fail with `storage_error` for 5 min | critical |
  | `InvalidTokenSpike` | more than 20 % of auth attempts (and over 1/s) use unknown tokens | warning |

  `todo_tests/integration/test_monitoring_assets.py` fails if either file queries a metric the
  app doesn't export.
