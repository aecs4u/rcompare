"""Compatibility shim — delegates to teczka.logger."""

from __future__ import annotations

from ..logger import get_logger, setup_logging

_log = get_logger("telemetry")


def configure_telemetry(service_name: str = "teczka") -> None:
    setup_logging()


def log_info(msg: str, **kwargs) -> None:
    _log.info(msg, **kwargs)


def log_warning(msg: str, **kwargs) -> None:
    _log.warning(msg, **kwargs)


def log_error(msg: str, **kwargs) -> None:
    _log.error(msg, **kwargs)


def log_exception(msg: str, **kwargs) -> None:
    _log.exception(msg, **kwargs)
