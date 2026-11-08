"""Integrated status bar combining status, filter pills, search, diff navigation, and progress."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

_SEARCH_DEBOUNCE_MS = 200

# Semantic colors for filter pill checked states
_PILL_COLORS: dict[str, str] = {
    "identical": "#4caf50",
    "different": "#e05a5a",
    "left_only": "#5b85dd",
    "right_only": "#d85a6a",
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
    background-color: {color_bg};
    color: white;
}}
QPushButton:hover {{
    background-color: palette(light);
}}
QPushButton:checked:hover {{
    background-color: {color};
    color: white;
}}
"""


def _make_pill(text: str, color: str) -> QPushButton:
    """Create a small checkable pill button with a colored checked state."""
    btn = QPushButton(text)
    btn.setCheckable(True)
    btn.setChecked(True)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    # Qt style sheets read 8-digit hex as #AARRGGBB, so build rgba() explicitly.
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    color_bg = f"rgba({r}, {g}, {b}, 204)"
    btn.setStyleSheet(_PILL_STYLE.format(color=color, color_bg=color_bg))
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
    search_mode_changed = Signal(str)
    filters_dialog_requested = Signal()
    newer_changed = Signal(
        str
    )  # "show_left_newer" | "show_right_newer" | "show_differences"
    navigate_prev = Signal()
    navigate_next = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self._status_detail_tooltip = ""
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
        self._status_label.setMinimumWidth(
            0
        )  # let the label shrink before the controls clip
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._status_label)

        # -- Inline progress bar (hidden by default) --
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(180)
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        layout.addWidget(_make_separator())

        # -- Center: filter pills --
        self._pill_identical = _make_pill("Identical", _PILL_COLORS["identical"])
        self._pill_different = _make_pill("Different", _PILL_COLORS["different"])
        self._pill_left_only = _make_pill("Left Only", _PILL_COLORS["left_only"])
        self._pill_right_only = _make_pill("Right Only", _PILL_COLORS["right_only"])

        for pill in (
            self._pill_identical,
            self._pill_different,
            self._pill_left_only,
            self._pill_right_only,
        ):
            layout.addWidget(pill)

        # Newer-side toggles (mutually exclusive, unchecked by default)
        self._pill_left_newer = _make_pill("◀ Newer", _PILL_COLORS["left_only"])
        self._pill_right_newer = _make_pill("Newer ▶", _PILL_COLORS["right_only"])
        for pill, tip in (
            (self._pill_left_newer, "Show only files newer on the left (LHS)"),
            (self._pill_right_newer, "Show only files newer on the right (RHS)"),
        ):
            pill.setChecked(False)
            pill.setToolTip(tip)
            layout.addWidget(pill)

        self._pill_file_filter = _make_pill("Filters", "#8e6bd6")
        self._pill_file_filter.setChecked(False)
        self._pill_file_filter.setToolTip("Edit file filters (include/exclude masks)")
        self._pill_file_filter.clicked.connect(self._on_filter_pill_clicked)
        layout.addWidget(self._pill_file_filter)

        layout.addWidget(_make_separator())

        # -- Search field --
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setMaximumWidth(110)
        self._search_edit.setFixedHeight(20)
        layout.addWidget(self._search_edit)

        self._search_mode_button = QToolButton()
        self._search_mode_button.setFixedSize(25, 22)
        self._search_mode_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._search_mode_menu = QMenu(self._search_mode_button)
        self._search_mode_group = QActionGroup(self._search_mode_menu)
        self._search_mode_group.setExclusive(True)
        self._search_mode_actions: dict[str, QAction] = {}
        for mode, label in (
            ("contains", "Contains"),
            ("wildcard", "Wildcard"),
            ("regex", "Regular expression"),
        ):
            action = QAction(label, self._search_mode_group)
            action.setCheckable(True)
            action.setData(mode)
            self._search_mode_group.addAction(action)
            self._search_mode_menu.addAction(action)
            self._search_mode_actions[mode] = action
        self._search_mode_group.triggered.connect(
            lambda action: self.set_search_mode(str(action.data()), emit=True)
        )
        self._search_mode_button.setMenu(self._search_mode_menu)
        layout.addWidget(self._search_mode_button)
        self.set_search_mode("contains")

        layout.addWidget(_make_separator())

        # -- Right: diff navigation --
        self._btn_prev = QToolButton()
        self._btn_prev.setText("\u25c0")
        self._btn_prev.setFixedSize(22, 22)
        self._btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._btn_prev)

        self._diff_pos_label = QLabel("0/0")
        self._diff_pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._diff_pos_label.setMinimumWidth(84)
        layout.addWidget(self._diff_pos_label)

        self._btn_next = QToolButton()
        self._btn_next.setText("\u25b6")
        self._btn_next.setFixedSize(22, 22)
        self._btn_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        self._pill_left_newer.toggled.connect(
            lambda on: self._on_newer_toggled(
                self._pill_left_newer, self._pill_right_newer, on
            )
        )
        self._pill_right_newer.toggled.connect(
            lambda on: self._on_newer_toggled(
                self._pill_right_newer, self._pill_left_newer, on
            )
        )

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(
            lambda: self.search_changed.emit(self._search_edit.text())
        )
        self._search_edit.textChanged.connect(self._search_debounce.start)
        self._btn_prev.clicked.connect(self.navigate_prev)
        self._btn_next.clicked.connect(self.navigate_next)

    def _on_newer_toggled(
        self, pill: QPushButton, other: QPushButton, on: bool
    ) -> None:
        if on and other.isChecked():
            other.blockSignals(True)
            other.setChecked(False)
            other.blockSignals(False)
        if not on:
            mode = "show_differences"
        else:
            mode = (
                "show_left_newer"
                if pill is self._pill_left_newer
                else "show_right_newer"
            )
        self.newer_changed.emit(mode)

    def _on_filter_pill_clicked(self) -> None:
        # The pill reflects whether a filter is active, not a user toggle.
        self._pill_file_filter.setChecked(not self._pill_file_filter.isChecked())
        self.filters_dialog_requested.emit()

    def set_file_filter_active(self, active: bool, tooltip: str = "") -> None:
        self._pill_file_filter.setChecked(active)
        self._pill_file_filter.setToolTip(
            f"File filter: {tooltip}"
            if active and tooltip
            else "Edit file filters (include/exclude masks)"
        )

    def set_newer_mode(self, mode: str) -> None:
        """Reflect the active newer-side mode without emitting signals."""
        for pill, active in (
            (self._pill_left_newer, mode == "show_left_newer"),
            (self._pill_right_newer, mode == "show_right_newer"),
        ):
            pill.blockSignals(True)
            pill.setChecked(active)
            pill.blockSignals(False)

    def _emit_filters_changed(self) -> None:
        self.filters_changed.emit(
            self._pill_identical.isChecked(),
            self._pill_different.isChecked(),
            self._pill_left_only.isChecked(),
            self._pill_right_only.isChecked(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_status(self, text: str) -> None:
        """Set the status message text."""
        self._status_label.setText(text)
        tooltip = (
            f"{text}\n\n{self._status_detail_tooltip}"
            if self._status_detail_tooltip
            else text
        )
        self._status_label.setToolTip(tooltip)

    def set_status_details(self, text: str) -> None:
        """Add persistent detail to the status-label tooltip."""
        self._status_detail_tooltip = text.strip()
        current = self._status_label.text()
        tooltip = (
            f"{current}\n\n{self._status_detail_tooltip}"
            if self._status_detail_tooltip
            else current
        )
        self._status_label.setToolTip(tooltip)

    def set_progress(self, value: int, maximum: int) -> None:
        """Set progress bar value and maximum."""
        self._progress_bar.setRange(0, maximum)
        self._progress_bar.setFormat("%p%")
        self._progress_bar.setValue(value)

    def set_busy_progress(self) -> None:
        """Show an animated progress bar while the worker has no percentage yet."""
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFormat("Scanning…")

    @property
    def progress_bar(self) -> QProgressBar:
        """Return the inline progress widget for compatibility with older callers."""
        return self._progress_bar

    def show_progress(self, visible: bool) -> None:
        """Show or hide the inline progress bar."""
        self._progress_bar.setVisible(visible)

    def set_diff_position(self, current: int, total: int) -> None:
        """Update the diff navigation position label (e.g. '3/12')."""
        self._diff_pos_label.setText(f"{current}/{total}")
        self._diff_pos_label.setToolTip(
            "Position among differing file entries. Folder entries are excluded."
        )

    def set_filter_state(
        self,
        identical: bool,
        different: bool,
        left_only: bool,
        right_only: bool,
    ) -> None:
        """Programmatically set the checked state of filter pills."""
        pills = (
            (self._pill_identical, identical),
            (self._pill_different, different),
            (self._pill_left_only, left_only),
            (self._pill_right_only, right_only),
        )
        for pill, checked in pills:
            pill.blockSignals(True)
            pill.setChecked(checked)
            pill.blockSignals(False)

    @property
    def search_text(self) -> str:
        """Current text in the search/filter field."""
        return self._search_edit.text()

    @property
    def search_mode(self) -> str:
        """Current search interpretation: contains, wildcard, or regex."""
        return self._search_mode

    def set_search_mode(self, mode: str, emit: bool = False) -> None:
        """Set the search mode and optionally notify the comparison window."""
        normalized = mode if mode in self._search_mode_actions else "contains"
        self._search_mode = normalized
        labels = {"contains": "C", "wildcard": "*", "regex": ".*"}
        names = {
            "contains": "Contains",
            "wildcard": "Wildcard",
            "regex": "Regular expression",
        }
        self._search_mode_button.setText(labels[normalized])
        self._search_mode_button.setToolTip(f"Search mode: {names[normalized]}")
        self._search_mode_actions[normalized].setChecked(True)
        if emit:
            self.search_mode_changed.emit(normalized)

    def set_search_text(self, text: str) -> None:
        """Set search text without starting a delayed user-edit signal."""
        self._search_debounce.stop()
        self._search_edit.blockSignals(True)
        self._search_edit.setText(text)
        self._search_edit.blockSignals(False)

    def set_search_error(self, error: str) -> None:
        """Show a malformed search expression on the search field."""
        invalid = bool(error)
        self._search_edit.setProperty("searchError", invalid)
        self._search_edit.setToolTip(error or "Filter file and folder names")
        self._search_edit.setStyleSheet(
            'QLineEdit[searchError="true"] { border: 1px solid #d9534f; }'
            if invalid
            else ""
        )
