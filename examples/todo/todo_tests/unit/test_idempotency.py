from datetime import timedelta

from todo_app.kernel import IDEMPOTENCY_TTL, IdempotencyRecord, fingerprint
from todo_tests.fakes import EPOCH


def test_fingerprint_parts_cannot_run_together() -> None:
    assert fingerprint("ab", "c") != fingerprint("a", "bc")
    assert fingerprint("a", "b") == fingerprint("a", "b")


def test_record_is_live_until_the_ttl_elapses() -> None:
    record = IdempotencyRecord(
        scope="s", key="k", request_fingerprint="f", resource_id="r", created_at=EPOCH
    )

    assert record.is_live(EPOCH + IDEMPOTENCY_TTL - timedelta(seconds=1))
    assert not record.is_live(EPOCH + IDEMPOTENCY_TTL)
