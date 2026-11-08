"""Generic QThread worker for running a blocking callable off the GUI thread."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal, Slot

from ..utils.telemetry import log_error


class FunctionWorker(QThread):
    """Runs ``func(*args, **kwargs)`` on a background thread.

    Emits ``finished`` with the return value on success, or ``error`` with
    the exception message on failure. Caller keeps a reference to the
    worker (e.g. as an instance attribute) until it finishes.
    """

    finished_with_result = Signal(object)
    error = Signal(str)
    _failure_details = Signal(str)

    def __init__(
        self,
        func: Callable[..., Any],
        *args: Any,
        parent=None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._failure_details.connect(self._log_failure)

    @Slot(str)
    def _log_failure(self, details: str) -> None:
        """Log a worker exception on the thread that owns this QObject."""
        log_error("background function worker failed", traceback=details)

    def run(self) -> None:
        try:
            result = self._func(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI thread
            self._failure_details.emit(traceback.format_exc())
            self.error.emit(str(exc))
            return
        self.finished_with_result.emit(result)
