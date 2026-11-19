import logging

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
