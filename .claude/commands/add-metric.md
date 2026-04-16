Add one or more Prometheus custom metrics for the instrumentation described below.

Arguments: $ARGUMENTS

## Instructions

Use the helpers in `src/metrics/registry.py`:

```python
from metrics.registry import counter, histogram

# Module-level singletons — define once, import anywhere
my_counter = counter("myapp_things_total", "Total things processed", ["status", "type"])
my_histogram = histogram(
    "myapp_operation_duration_seconds",
    "Duration of operation",
    ["operation"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
```

### Naming conventions (Prometheus best practices)
- Use `snake_case`
- Suffix counters with `_total`
- Suffix histograms/summaries with `_seconds` or `_bytes` where applicable
- Prefix with your app/domain name to avoid collisions
- Keep label cardinality low — no user IDs, request IDs, or unbounded strings as labels

### Where to define them
- For domain metrics tied to a specific module: define at the top of that module
- For cross-cutting metrics: create `src/metrics/<domain>.py` and import from there

### Incrementing / observing
```python
my_counter.labels(status="success", type="order").inc()
my_histogram.labels(operation="db_query").observe(elapsed_seconds)
```

### After implementation
- Verify the metric appears in `GET /metrics` by starting the dev server (`make dev`) and checking `curl http://localhost:8000/metrics | grep <metric_name>`
- Write a test that calls the instrumented code path and checks the counter value via `prometheus_client.REGISTRY`
- Run `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/`
