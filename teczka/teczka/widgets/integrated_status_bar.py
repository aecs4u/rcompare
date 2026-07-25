"""Integrated status bar combining status, filter pills, search, diff navigation, and progress."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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
    background-color: palette(mid);
    color: palette(mid);
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
    color_bg = color + "cc"
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
    navigate_prev = Signal()
    navigate_next = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
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
        layout.addWidget(self._status_label)

        # -- Inline progress bar (hidden by default) --
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(120)
        self._progress_bar.setFixedHeight(14)
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

        layout.addWidget(_make_separator())

        # -- Search field --
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setMaximumWidth(150)
        self._search_edit.setFixedHeight(20)
        layout.addWidget(self._search_edit)

        layout.addWidget(_make_separator())

        # -- Right: diff navigation --
        self._btn_prev = QToolButton()
        self._btn_prev.setText("\u25c0")
        self._btn_prev.setFixedSize(22, 22)
        self._btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._btn_prev)

        self._diff_pos_label = QLabel("0/0")
        self._diff_pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._diff_pos_label.setMinimumWidth(36)
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

        self._search_edit.textChanged.connect(self.search_changed)
        self._btn_prev.clicked.connect(self.navigate_prev)
        self._btn_next.clicked.connect(self.navigate_next)

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

    def set_progress(self, value: int, maximum: int) -> None:
        """Set progress bar value and maximum."""
        self._progress_bar.setRange(0, maximum)
        self._progress_bar.setValue(value)

    def show_progress(self, visible: bool) -> None:
        """Show or hide the inline progress bar."""
        self._progress_bar.setVisible(visible)

    def set_diff_position(self, current: int, total: int) -> None:
        """Update the diff navigation position label (e.g. '3/12')."""
        self._diff_pos_label.setText(f"{current}/{total}")

    def set_filter_state(
        self,
        identical: bool,
        different: bool,
        left_only: bool,
        right_only: bool,
    ) -> None:
        """Programmatically set the checked state of filter pills."""
        self._pill_identical.setChecked(identical)
        self._pill_different.setChecked(different)
        self._pill_left_only.setChecked(left_only)
        self._pill_right_only.setChecked(right_only)

    @property
    def search_text(self) -> str:
        """Current text in the search/filter field."""
        return self._search_edit.text()
