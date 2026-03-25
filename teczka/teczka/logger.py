"""Structured logging module for teczka.

Uses *structlog* when available, falling back to stdlib :mod:`logging`.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

try:
    import structlog  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency at runtime
    structlog = None  # type: ignore[assignment]

_configured = False


def setup_logging(
    log_level: str = "INFO",
    log_file: str | None = None,
) -> None:
    """Configure the logging subsystem.

    Parameters
    ----------
    log_level:
        Root log level (default taken from ``RCOMPARE_LOG_LEVEL`` env-var,
        then the *log_level* argument, then ``"INFO"``).
    log_file:
        Optional path to a log file.  When *structlog* is available the file
        receives JSON-formatted lines; otherwise a human-readable format is
        used.
    """
    global _configured
    if _configured:
        return

    level_name = os.environ.get("RCOMPARE_LOG_LEVEL", log_level).upper()
    level = getattr(logging, level_name, logging.INFO)

    if structlog is not None:
        _configure_structlog(level, log_file)
    else:
        _configure_stdlib(level, log_file)

    _configured = True


# ------------------------------------------------------------------
# structlog helpers
# ------------------------------------------------------------------

def _configure_structlog(level: int, log_file: str | None) -> None:
    """Set up *structlog* with console + optional JSON file output."""
    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Console handler — human-readable coloured output.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)

    handlers: list[logging.Handler] = [console_handler]

    if log_file is not None:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=handlers,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Attach formatters to handlers so each gets the right renderer.
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
        foreign_pre_chain=shared_processors,
    )
    console_handler.setFormatter(console_formatter)

    if log_file is not None:
        json_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
        handlers[-1].setFormatter(json_formatter)


# ------------------------------------------------------------------
# stdlib-only helpers
# ------------------------------------------------------------------

_STDLIB_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _configure_stdlib(level: int, log_file: str | None) -> None:
    """Set up stdlib :mod:`logging` with a clean format."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if log_file is not None:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format=_STDLIB_FMT,
        handlers=handlers,
    )

    root = logging.getLogger()
    root.info("structlog not installed; using stdlib logging only")


# ------------------------------------------------------------------
# Public logger factory
# ------------------------------------------------------------------

def get_logger(name: str) -> Any:
    """Return a logger bound to *name*.

    When *structlog* is available this returns a
    :class:`structlog.stdlib.BoundLogger`; otherwise a stdlib
    :class:`logging.Logger`.
    """
    if structlog is not None:
        return structlog.get_logger(name)
    return logging.getLogger(name)
