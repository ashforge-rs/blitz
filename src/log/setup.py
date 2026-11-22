import json as _json
import logging
import sys
from datetime import UTC
from typing import TYPE_CHECKING, Any, TextIO

import loguru
from loguru import logger as _logger

if TYPE_CHECKING:
    from loguru import Message, Record

_CORE_FIELDS = ("time", "level", "logger", "message", "exception")


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


def _to_json_line(record: Record, exception: str) -> str:
    """One flat JSON object: core fields first, then the bound ``extra`` fields.

    Fields whose value is ``None`` or an empty dict/list are left out. A bound field named like
    a core one never overwrites it: it is kept as ``extra_<name>``.
    """
    extra = {
        k if k not in _CORE_FIELDS or k == "logger" else f"extra_{k}": v
        for k, v in record["extra"].items()
    }
    payload: dict[str, Any] = {
        "time": record["time"]
        .astimezone(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "level": record["level"].name,
        "logger": extra.pop("logger", None) or record["name"],
        "message": record["message"],
        "exception": exception or None,
        **extra,
    }
    payload = {k: v for k, v in payload.items() if v is not None and v != {} and v != []}
    return _json.dumps(payload, default=str, ensure_ascii=False)


class _JsonLinesSink:
    """Writes each record as one JSON line.

    The sink's format is ``""``, so Loguru hands over only the rendered traceback (it appends
    ``{exception}`` itself). The traceback is rendered in the logging thread, because with
    ``enqueue=True`` the record reaches the sink pickled, without its traceback object.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def __call__(self, message: Message) -> None:
        self._stream.write(_to_json_line(message.record, str(message).strip()) + "\n")
        self._stream.flush()


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    _logger.remove()

    if json:
        # diagnose=False: tracebacks must not print local variables (secrets) into logs.
        _logger.add(
            _JsonLinesSink(sys.stdout),
            level=level,
            format="",
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )
    else:
        _logger.add(
            sys.stdout,
            level=level,
            colorize=True,
            enqueue=True,
        )

    # Intercept all stdlib logging. Loggers without handlers propagate to the
    # root intercept handler. Loggers that have their own handlers (e.g. those
    # uvicorn configures) get them swapped for the intercept handler.
    #
    # Loggers that were deliberately silenced (no handlers, propagate=False,
    # which is how uvicorn's --no-access-log disables "uvicorn.access") are left
    # alone. Re-attaching a handler would turn them back on.
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in list(logging.root.manager.loggerDict):
        log = logging.getLogger(name)
        if log.handlers:
            log.handlers = [_InterceptHandler()]
            log.propagate = False


def get_logger(name: str) -> loguru.Logger:
    return _logger.bind(logger=name)
