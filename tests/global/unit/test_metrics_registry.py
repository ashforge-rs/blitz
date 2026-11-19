from metrics import counter, histogram


def test_counter_is_idempotent():
    first = counter("blitz_test_jobs_total", "jobs", ["status"])
    assert counter("blitz_test_jobs_total", "jobs", ["status"]) is first
    first.labels(status="ok").inc()


def test_histogram_is_idempotent_with_custom_buckets():
    first = histogram("blitz_test_latency_seconds", "latency", buckets=(0.1, 1.0))
    assert histogram("blitz_test_latency_seconds", "latency") is first
    first.observe(0.5)
