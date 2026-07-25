"""Generic QThread worker for running a blocking callable off the GUI thread."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from ..utils.telemetry import log_exception


class FunctionWorker(QThread):
    """Runs ``func(*args, **kwargs)`` on a background thread.

    Emits ``finished`` with the return value on success, or ``error`` with
    the exception message on failure. Caller keeps a reference to the
    worker (e.g. as an instance attribute) until it finishes.
    """

    finished_with_result = Signal(object)
    error = Signal(str)

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

    def run(self) -> None:
        try:
            result = self._func(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI thread
            log_exception("background function worker failed")
            self.error.emit(str(exc))
            return
        self.finished_with_result.emit(result)
