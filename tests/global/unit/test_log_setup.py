import io
import json
import logging
import sys

import pytest
from loguru import logger

from log.setup import configure_logging


@pytest.fixture
def stdlib_logger():
    """A throwaway stdlib logger, cleaned up afterwards."""
    names: list[str] = []

    def make(name, *, handlers=(), propagate=True):
        names.append(name)
        log = logging.getLogger(name)
        log.handlers = list(handlers)
        log.propagate = propagate
        return log

    yield make
    for name in names:
        log = logging.getLogger(name)
        log.handlers = []
        log.propagate = True


def test_silenced_logger_stays_silent(stdlib_logger):
    # Mirrors uvicorn --no-access-log: no handlers, propagate=False.
    stdlib_logger("blitz.test.silenced", propagate=False)
    configure_logging(level="DEBUG")
    records: list[str] = []
    sink = logger.add(lambda m: records.append(m.record["message"]), level="DEBUG")
    try:
        logging.getLogger("blitz.test.silenced").warning("should not appear")
    finally:
        logger.remove(sink)
        configure_logging(level="WARNING")
    assert "should not appear" not in records


def test_logger_with_handlers_is_intercepted_once(stdlib_logger):
    stdlib_logger("blitz.test.handled", handlers=[logging.NullHandler()])
    configure_logging(level="DEBUG")
    records: list[str] = []
    sink = logger.add(lambda m: records.append(m.record["message"]), level="DEBUG")
    try:
        logging.getLogger("blitz.test.handled").warning("hello")
    finally:
        logger.remove(sink)
        configure_logging(level="WARNING")
    assert records.count("hello") == 1


def test_plain_logger_propagates_to_loguru(stdlib_logger):
    stdlib_logger("blitz.test.plain")
    configure_logging(level="DEBUG")
    records: list[str] = []
    sink = logger.add(lambda m: records.append(m.record["message"]), level="DEBUG")
    try:
        logging.getLogger("blitz.test.plain").warning("propagated")
    finally:
        logger.remove(sink)
        configure_logging(level="WARNING")
    assert records.count("propagated") == 1


@pytest.fixture
def json_lines(monkeypatch):
    """Configure JSON logging into a buffer; returns a function that reads the parsed lines."""
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    configure_logging(level="DEBUG", json=True)

    def read() -> list[dict]:
        logger.complete()
        return [json.loads(line) for line in out.getvalue().splitlines() if line]

    yield read
    monkeypatch.undo()
    configure_logging(level="WARNING")


def test_json_lines_are_flat_with_extra_fields_at_the_top(json_lines):
    logger.bind(logger="orders", order_id="o-1", note=None, tags={}).info("order placed")

    [line] = json_lines()
    assert line.keys() == {"time", "level", "logger", "message", "order_id"}
    assert line["time"].endswith("Z")
    assert (line["level"], line["logger"], line["message"], line["order_id"]) == (
        "INFO",
        "orders",
        "order placed",
        "o-1",
    )


def test_json_lines_carry_the_traceback_as_one_field(json_lines):
    try:
        1 / 0  # noqa: B018
    except ZeroDivisionError:
        logger.exception("boom")

    [line] = json_lines()
    assert line["message"] == "boom"
    assert line["exception"].startswith("Traceback")
    assert line["exception"].endswith("ZeroDivisionError: division by zero")


def test_fields_named_like_core_ones_are_kept_without_overwriting(json_lines):
    logger.bind(level="spoofed", message="db said No").warning("real")

    [line] = json_lines()
    assert (line["level"], line["message"]) == ("WARNING", "real")
    assert (line["extra_level"], line["extra_message"]) == ("spoofed", "db said No")
