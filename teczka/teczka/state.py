"""Central application state manager for Teczka.

Follows the Kalka/Czkawka pattern: a single QObject that owns all
application state, emits signals on changes, and persists settings.
All views and workers connect to these signals instead of reaching
into each other directly.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any

from PySide6.QtCore import QObject, Signal

from .utils.config import AppConfig


class CompareState(Enum):
    """State machine for comparison lifecycle."""

    IDLE = auto()
    COMPARING = auto()
    STOPPING = auto()


class ActiveView(Enum):
    """Which comparison view is active."""

    HOME = auto()
    FOLDER = auto()
    TEXT = auto()
    HEX = auto()
    IMAGE = auto()
    TABLE = auto()
    MERGE = auto()


class AppState(QObject):
    """Central application state.

    Signals
    -------
    view_changed(object)
        Emitted when the active view changes (passes ActiveView enum).
    compare_started()
        Comparison operation began.
    compare_finished()
        Comparison operation ended (success or cancel).
    compare_progress(object)
        Progress update during comparison (passes ProgressInfo dict).
    results_updated()
        New comparison results are available.
    settings_changed()
        User settings were modified.
    paths_changed()
        Left/right/base paths were updated.
    bookmarks_changed()
        Bookmarks list was modified.
    error_occurred(str)
        An error message for the user.
    info_message(str)
        An informational status message.
    """

    # Lifecycle signals
    view_changed = Signal(object)
    compare_started = Signal()
    compare_finished = Signal()
    compare_progress = Signal(object)
    results_updated = Signal()

    # Configuration signals
    settings_changed = Signal()
    paths_changed = Signal()
    bookmarks_changed = Signal()

    # User feedback
    error_occurred = Signal(str)
    info_message = Signal(str)

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or AppConfig.load()
        self._compare_state = CompareState.IDLE
        self._active_view = ActiveView.HOME
        self._left_path = self.config.last_paths.get("left", "")
        self._right_path = self.config.last_paths.get("right", "")
        self._base_path = self.config.last_paths.get("base", "")
        self._results: dict[str, Any] = {}

    # ── View management ──────────────────────────────────────────

    @property
    def active_view(self) -> ActiveView:
        return self._active_view

    def set_active_view(self, view: ActiveView) -> None:
        if view != self._active_view:
            self._active_view = view
            self.view_changed.emit(view)

    # ── Comparison lifecycle ─────────────────────────────────────

    @property
    def comparing(self) -> bool:
        return self._compare_state == CompareState.COMPARING

    @property
    def stop_requested(self) -> bool:
        return self._compare_state == CompareState.STOPPING

    @property
    def compare_state(self) -> CompareState:
        return self._compare_state

    def set_comparing(self, comparing: bool) -> None:
        if comparing:
            self._compare_state = CompareState.COMPARING
            self.compare_started.emit()
        else:
            self._compare_state = CompareState.IDLE
            self.compare_finished.emit()

    def request_stop(self) -> None:
        if self._compare_state == CompareState.COMPARING:
            self._compare_state = CompareState.STOPPING

    def update_progress(self, progress: Any) -> None:
        self.compare_progress.emit(progress)

    # ── Path management ──────────────────────────────────────────

    @property
    def left_path(self) -> str:
        return self._left_path

    @left_path.setter
    def left_path(self, value: str) -> None:
        if value != self._left_path:
            self._left_path = value
            self.config.last_paths["left"] = value
            self.paths_changed.emit()

    @property
    def right_path(self) -> str:
        return self._right_path

    @right_path.setter
    def right_path(self, value: str) -> None:
        if value != self._right_path:
            self._right_path = value
            self.config.last_paths["right"] = value
            self.paths_changed.emit()

    @property
    def base_path(self) -> str:
        return self._base_path

    @base_path.setter
    def base_path(self, value: str) -> None:
        if value != self._base_path:
            self._base_path = value
            self.config.last_paths["base"] = value
            self.paths_changed.emit()

    # ── Results ──────────────────────────────────────────────────

    def set_results(self, key: str, data: Any) -> None:
        self._results[key] = data
        self.results_updated.emit()

    def get_results(self, key: str) -> Any:
        return self._results.get(key)

    def clear_results(self) -> None:
        self._results.clear()
        self.results_updated.emit()

    # ── Bookmarks ────────────────────────────────────────────────

    def add_bookmark(self, name: str, left: str, right: str) -> None:
        self.config.bookmarks.append(
            {"name": name, "left": left, "right": right}
        )
        self.bookmarks_changed.emit()

    def remove_bookmark(self, index: int) -> None:
        if 0 <= index < len(self.config.bookmarks):
            self.config.bookmarks.pop(index)
            self.bookmarks_changed.emit()

    # ── Persistence ──────────────────────────────────────────────

    def save_settings(self) -> None:
        self.config.save()
        self.settings_changed.emit()

    def load_settings(self) -> None:
        self.config = AppConfig.load()
        self._left_path = self.config.last_paths.get("left", "")
        self._right_path = self.config.last_paths.get("right", "")
        self._base_path = self.config.last_paths.get("base", "")
        self.settings_changed.emit()
