"""Integrated status bar combining status, filter pills, search, diff navigation, and progress.

This widget is the application's only status surface. The native
``QMainWindow`` status bar is hidden, so anything that calls
``statusBar().showMessage()`` is invisible to the user — route messages,
progress and navigation position through :meth:`show_message`,
:meth:`set_progress` and :meth:`set_navigation_position` instead.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

_SEARCH_DEBOUNCE_MS = 200

# Semantic colours for the checked state of each filter pill.
#
# Darkened from the original palette so white pill text clears the WCAG AA
# 4.5:1 contrast ratio for normal text; the previous values measured
# 2.78:1 (green), 3.63:1 (red), 3.59:1 (blue) and 3.76:1 (right-only red).
# tests/test_accessibility.py pins the measured ratios.
_PILL_COLORS: dict[str, str] = {
    "identical": "#2e7d32",
    "different": "#b3261e",
    "left_only": "#1f4fa8",
    "right_only": "#a4203a",
}

# A non-colour marker per status, so the pills stay distinguishable in
# monochrome and under common colour-vision deficiencies.
_PILL_MARKERS: dict[str, str] = {
    "identical": "=",
    "different": "≠",  # not equal
    "left_only": "◀",  # left-pointing triangle
    "right_only": "▶",  # right-pointing triangle
}

_PILL_STYLE = """
QPushButton {{
    border: 1px solid palette(mid);
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    background-color: palette(button);
    color: palette(button-text);
    min-height: 18px;
    max-height: 18px;
}}
QPushButton:checked {{
    border: 1px solid {color};
    background-color: {color};
    color: white;
}}
QPushButton:hover {{
    background-color: palette(light);
}}
QPushButton:checked:hover {{
    background-color: {color};
    color: white;
}}
QPushButton:focus {{
    border: 2px solid palette(highlight);
}}
"""


def _make_pill(text: str, color: str, marker: str) -> QPushButton:
    """Create a small checkable pill button with a colored checked state."""
    btn = QPushButton(f"{marker} {text}")
    btn.setCheckable(True)
    btn.setChecked(True)
    # Keyboard reachable: these are primary filter controls, and NoFocus made
    # the whole filter row unusable without a mouse.
    btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    btn.setAccessibleName(f"Show {text.lower()} items")
    btn.setAccessibleDescription(
        f"Toggle visibility of {text.lower()} rows in the folder comparison"
    )
    btn.setToolTip(f"Show or hide {text.lower()} rows")
    btn.setStyleSheet(_PILL_STYLE.format(color=color))
    return btn


def _make_separator() -> QFrame:
    """Create a thin vertical separator."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    sep.setFixedWidth(2)
    return sep


class IntegratedStatusBar(QWidget):
    """Compact bottom bar combining status, filters, search, diff nav, and progress."""

    filters_changed = Signal(bool, bool, bool, bool)
    search_changed = Signal(str)
    navigate_prev = Signal()
    navigate_next = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self._persistent_message = "Ready"
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        # -- Left: status message --
        self._status_label = QLabel("Ready")
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._status_label.setAccessibleName("Status message")
        layout.addWidget(self._status_label)

        # -- Stage label for structured progress (hidden until used) --
        self._stage_label = QLabel("")
        self._stage_label.setVisible(False)
        self._stage_label.setAccessibleName("Operation stage")
        layout.addWidget(self._stage_label)

        # -- Inline progress bar (hidden by default) --
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(120)
        self._progress_bar.setFixedHeight(14)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setVisible(False)
        self._progress_bar.setAccessibleName("Operation progress")
        layout.addWidget(self._progress_bar)

        layout.addWidget(_make_separator())

        # -- Center: filter pills --
        self._pill_identical = _make_pill(
            "Identical", _PILL_COLORS["identical"], _PILL_MARKERS["identical"]
        )
        self._pill_different = _make_pill(
            "Different", _PILL_COLORS["different"], _PILL_MARKERS["different"]
        )
        self._pill_left_only = _make_pill(
            "Left Only", _PILL_COLORS["left_only"], _PILL_MARKERS["left_only"]
        )
        self._pill_right_only = _make_pill(
            "Right Only", _PILL_COLORS["right_only"], _PILL_MARKERS["right_only"]
        )

        for pill in (
            self._pill_identical,
            self._pill_different,
            self._pill_left_only,
            self._pill_right_only,
        ):
            layout.addWidget(pill)

        layout.addWidget(_make_separator())

        # -- Search field --
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setMaximumWidth(150)
        self._search_edit.setFixedHeight(20)
        self._search_edit.setAccessibleName("Filter by name")
        self._search_edit.setToolTip("Filter rows by name (Ctrl+F)")
        layout.addWidget(self._search_edit)

        layout.addWidget(_make_separator())

        # -- Right: diff navigation --
        self._btn_prev = QToolButton()
        self._btn_prev.setText("◀")
        self._btn_prev.setFixedSize(22, 22)
        self._btn_prev.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._btn_prev.setAccessibleName("Previous difference")
        self._btn_prev.setToolTip("Previous difference (Alt+Up)")
        layout.addWidget(self._btn_prev)

        self._diff_pos_label = QLabel("0/0")
        self._diff_pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._diff_pos_label.setMinimumWidth(36)
        self._diff_pos_label.setAccessibleName("Difference position")
        layout.addWidget(self._diff_pos_label)

        self._btn_next = QToolButton()
        self._btn_next.setText("▶")
        self._btn_next.setFixedSize(22, 22)
        self._btn_next.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._btn_next.setAccessibleName("Next difference")
        self._btn_next.setToolTip("Next difference (Alt+Down)")
        layout.addWidget(self._btn_next)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        for pill in (
            self._pill_identical,
            self._pill_different,
            self._pill_left_only,
            self._pill_right_only,
        ):
            pill.toggled.connect(self._emit_filters_changed)

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(
            lambda: self.search_changed.emit(self._search_edit.text())
        )
        self._search_edit.textChanged.connect(self._search_debounce.start)
        self._btn_prev.clicked.connect(self.navigate_prev)
        self._btn_next.clicked.connect(self.navigate_next)

        # Restores the persistent summary after a timed message expires.
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self._restore_persistent_message)

    def _emit_filters_changed(self) -> None:
        self.filters_changed.emit(
            self._pill_identical.isChecked(),
            self._pill_different.isChecked(),
            self._pill_left_only.isChecked(),
            self._pill_right_only.isChecked(),
        )

    def _restore_persistent_message(self) -> None:
        self._status_label.setText(self._persistent_message)

    # ------------------------------------------------------------------
    # Public API — status and progress
    # ------------------------------------------------------------------

    def show_message(self, text: str, timeout_ms: int = 0) -> None:
        """Show *text*, reverting to the persistent summary after *timeout_ms*.

        This is the replacement for ``QMainWindow.statusBar().showMessage()``,
        which writes to a hidden widget. A ``timeout_ms`` of 0 means the
        message stays until something else replaces it.
        """
        self._message_timer.stop()
        self._status_label.setText(text)
        if timeout_ms > 0:
            self._message_timer.start(timeout_ms)

    def set_status(self, text: str) -> None:
        """Set the persistent status summary (survives timed messages)."""
        self._persistent_message = text
        self._message_timer.stop()
        self._status_label.setText(text)

    @property
    def message(self) -> str:
        """Current visible status text (used by tests and session capture)."""
        return self._status_label.text()

    def set_progress(self, value: int, maximum: int = 100) -> None:
        """Set progress bar value and maximum, showing the bar if hidden."""
        self._progress_bar.setRange(0, maximum)
        self._progress_bar.setValue(value)
        if not self._progress_bar.isVisible():
            self._progress_bar.setVisible(True)

    @property
    def progress_value(self) -> int:
        return self._progress_bar.value()

    def show_progress(self, visible: bool) -> None:
        """Show or hide the inline progress bar."""
        self._progress_bar.setVisible(visible)
        if not visible:
            self._progress_bar.setValue(0)
            self.set_stage("")

    def set_stage(self, label: str) -> None:
        """Show the current operation stage next to the progress bar."""
        self._stage_label.setText(label)
        self._stage_label.setVisible(bool(label))

    @property
    def stage(self) -> str:
        return self._stage_label.text()

    def set_navigation_position(self, current: int, total: int) -> None:
        """Update the difference-navigation counter (e.g. ``3/12``)."""
        self._diff_pos_label.setText(f"{current}/{total}")
        self._btn_prev.setEnabled(total > 0)
        self._btn_next.setEnabled(total > 0)

    # Retained name from the original API; some call sites read better with it.
    set_diff_position = set_navigation_position

    @property
    def navigation_position(self) -> str:
        return self._diff_pos_label.text()

    # ------------------------------------------------------------------
    # Public API — filters
    # ------------------------------------------------------------------

    def set_filter_state(
        self,
        identical: bool,
        different: bool,
        left_only: bool,
        right_only: bool,
    ) -> None:
        """Set the checked state of the pills without re-emitting signals.

        Callers are pushing already-applied state down; re-emitting would feed
        it straight back into the handler that just set it.
        """
        for pill, checked in (
            (self._pill_identical, identical),
            (self._pill_different, different),
            (self._pill_left_only, left_only),
            (self._pill_right_only, right_only),
        ):
            pill.blockSignals(True)
            pill.setChecked(checked)
            pill.blockSignals(False)

    def set_search_text(self, text: str) -> None:
        """Set the search field without re-triggering the debounced signal."""
        if self._search_edit.text() == text:
            return
        self._search_edit.blockSignals(True)
        self._search_edit.setText(text)
        self._search_edit.blockSignals(False)

    def focus_search(self) -> None:
        """Give keyboard focus to the visible search field (Ctrl+F target)."""
        self._search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search_edit.selectAll()

    def clear_search(self) -> None:
        self._search_edit.clear()

    def set_filters_enabled(self, enabled: bool) -> None:
        """Enable/disable the folder-only filter controls.

        The pills and the name filter only mean anything in Folder Compare;
        leaving them live in Text/Hex/Image/Table implies they do something.
        """
        for widget in (
            self._pill_identical,
            self._pill_different,
            self._pill_left_only,
            self._pill_right_only,
            self._search_edit,
        ):
            widget.setEnabled(enabled)

    @property
    def search_text(self) -> str:
        """Current text in the search/filter field."""
        return self._search_edit.text()
