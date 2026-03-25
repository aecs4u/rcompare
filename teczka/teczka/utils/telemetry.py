"""Application telemetry/logging helpers built around logfire."""

from __future__ import annotations

import logging
import os
from typing import Any

try:
    import logfire  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency at runtime
    logfire = None

_configured = False
_logger = logging.getLogger("teczka")


def configure_telemetry(service_name: str = "teczka") -> None:
    """Configure stdlib logging and logfire (when available)."""
    global _configured
    if _configured:
        return

    level_name = os.environ.get("RCOMPARE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if logfire is None:
        _logger.info("logfire not installed; using stdlib logging only")
        _configured = True
        return

    configured = False
    attempts: list[dict[str, Any]] = [
        {"service_name": service_name, "send_to_logfire": "if-token-present"},
        {"send_to_logfire": "if-token-present"},
        {},
    ]
    for kwargs in attempts:
        try:
            logfire.configure(**kwargs)
            configured = True
            break
        except TypeError:
            # Signature variations across logfire versions.
            continue
        except Exception:
            _logger.exception("logfire configure failed")
            break

    if configured:
        _logger.info("logfire configured for telemetry")
        _safe_logfire("info", "telemetry configured", service_name=service_name)
    else:
        _logger.warning("logfire unavailable; continuing with stdlib logging")

    _configured = True


def log_info(message: str, **attrs: Any) -> None:
    _logger.info("%s %s", message, attrs if attrs else "")
    _safe_logfire("info", message, **attrs)


def log_warning(message: str, **attrs: Any) -> None:
    _logger.warning("%s %s", message, attrs if attrs else "")
    _safe_logfire("warning", message, **attrs)


def log_error(message: str, **attrs: Any) -> None:
    _logger.error("%s %s", message, attrs if attrs else "")
    _safe_logfire("error", message, **attrs)


def log_exception(message: str, **attrs: Any) -> None:
    _logger.exception("%s %s", message, attrs if attrs else "")
    _safe_logfire("exception", message, **attrs)


def _safe_logfire(level: str, message: str, **attrs: Any) -> None:
    if logfire is None:
        return
    try:
        fn = getattr(logfire, level, None)
        if callable(fn):
            fn(message, **attrs)
    except Exception:
        # Never fail app flow because telemetry failed.
        _logger.debug("logfire emit failed", exc_info=True)

