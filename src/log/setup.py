from __future__ import annotations

import logging
import sys

import loguru
from loguru import logger as _logger


class _InterceptHandler(logging.Handler):
    """Route stdlib logging records through Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        _logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(level: str = "INFO", json: bool = False) -> None:
    _logger.remove()

    if json:
        _logger.add(
            sys.stdout,
            level=level,
            serialize=True,
            enqueue=True,
        )
    else:
        _logger.add(
            sys.stdout,
            level=level,
            colorize=True,
            enqueue=True,
        )

    # Intercept all stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in list(logging.root.manager.loggerDict):
        log = logging.getLogger(name)
        log.handlers = [_InterceptHandler()]
        log.propagate = False


def get_logger(name: str) -> loguru.Logger:
    return _logger.bind(logger=name)
