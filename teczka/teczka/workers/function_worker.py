"""Generic QThread worker for running a blocking callable off the GUI thread."""

from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from ..utils.telemetry import log_exception


class CancelledError(RuntimeError):
    """Raised inside the worker function when the caller requested a cancel."""


class CancelToken:
    """Cooperative cancellation flag shared with the worker function.

    Long parses (CSV/Excel/image statistics) previously could only be
    orphaned: :class:`FunctionWorker` had no cancellation path at all, so a
    cancelled operation kept running and kept its result. A worker function
    that accepts a ``cancel_token`` keyword receives one of these and is
    expected to call :meth:`check` (or test :meth:`is_set`) between work units.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        """Raise :class:`CancelledError` if cancellation has been requested."""
        if self._event.is_set():
            raise CancelledError("operation cancelled")


class FunctionWorker(QThread):
    """Runs ``func(*args, **kwargs)`` on a background thread.

    Emits ``finished_with_result`` with the return value on success, or
    ``error`` with the exception message on failure. Caller keeps a reference
    to the worker (e.g. as an instance attribute) until it finishes.

    Pass ``cancellable=True`` to hand *func* a ``cancel_token`` keyword
    argument; :meth:`cancel` then sets it and the worker emits ``cancelled``
    instead of a result. Without cooperation from *func*, :meth:`cancel` still
    suppresses the result so a cancelled operation cannot update the GUI.
    """

    finished_with_result = Signal(object)
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        func: Callable[..., Any],
        *args: Any,
        parent=None,
        cancellable: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._token = CancelToken()
        self._cancellable = cancellable

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation.

        Safe to call from the GUI thread at any time, including after the
        worker has finished.
        """
        self._token.cancel()

    def is_cancelled(self) -> bool:
        return self._token.is_set()

    @property
    def cancel_token(self) -> CancelToken:
        return self._token

    # ------------------------------------------------------------------
    # QThread
    # ------------------------------------------------------------------

    def run(self) -> None:
        kwargs = dict(self._kwargs)
        if self._cancellable:
            kwargs["cancel_token"] = self._token
        try:
            result = self._func(*self._args, **kwargs)
        except CancelledError:
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI thread
            if self._token.is_set():
                # A failure caused by teardown during cancellation is not a
                # user-visible error.
                self.cancelled.emit()
                return
            log_exception("background function worker failed")
            self.error.emit(str(exc))
            return
        # Even an uncooperative function must not deliver a result the user
        # already cancelled.
        if self._token.is_set():
            self.cancelled.emit()
            return
        self.finished_with_result.emit(result)
