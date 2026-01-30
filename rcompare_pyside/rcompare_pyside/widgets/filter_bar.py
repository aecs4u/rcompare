"""FilterBar widget providing toggle buttons and a search field for result filtering."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QToolButton,
    QWidget,
)

# Indicator colors matching the Slint scheme
COLOR_IDENTICAL = "#4caf50"
COLOR_DIFFERENT = "#e05a5a"
COLOR_LEFT_ONLY = "#5b85dd"
COLOR_RIGHT_ONLY = "#d85a6a"

_BUTTON_STYLE_TEMPLATE = """
QToolButton {{
    border: 1px solid #aaaaaa;
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 12px;
    background-color: #f0f0f0;
    color: #333333;
}}
QToolButton:checked {{
    border: 2px solid {color};
    background-color: {color_bg};
    color: #ffffff;
    font-weight: bold;
}}
QToolButton:hover {{
    background-color: #e0e0e0;
}}
QToolButton:checked:hover {{
    background-color: {color};
}}
"""


def _make_toggle(text: str, color: str, *, checked: bool = True) -> QToolButton:
    """Create a compact, checkable QToolButton with a colored checked state."""
    btn = QToolButton()
    btn.setText(text)
    btn.setCheckable(True)
    btn.setChecked(checked)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    # Derive a lighter background for the checked-but-not-hovered state
    color_bg = color + "cc"  # ~80 % opacity via RGBA hex shorthand
    btn.setStyleSheet(
        _BUTTON_STYLE_TEMPLATE.format(color=color, color_bg=color_bg)
    )
    return btn


class FilterBar(QWidget):
    """Horizontal bar with filter toggle buttons and a text search field."""

    # (show_identical, show_different, show_left_only, show_right_only, search_text)
    filters_changed = Signal(bool, bool, bool, bool, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Toggle buttons ---
        self._btn_identical = _make_toggle("Identical", COLOR_IDENTICAL)
        self._btn_different = _make_toggle("Different", COLOR_DIFFERENT)
        self._btn_left_only = _make_toggle("Left Only", COLOR_LEFT_ONLY)
        self._btn_right_only = _make_toggle("Right Only", COLOR_RIGHT_ONLY)

        layout.addWidget(self._btn_identical)
        layout.addWidget(self._btn_different)
        layout.addWidget(self._btn_left_only)
        layout.addWidget(self._btn_right_only)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # --- Search field ---
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter...")
        self._search_edit.setClearButtonEnabled(True)
        layout.addWidget(self._search_edit, 1)  # stretch factor 1

        # --- Connections ---
        self._btn_identical.toggled.connect(self._emit_filters_changed)
        self._btn_different.toggled.connect(self._emit_filters_changed)
        self._btn_left_only.toggled.connect(self._emit_filters_changed)
        self._btn_right_only.toggled.connect(self._emit_filters_changed)
        self._search_edit.textChanged.connect(self._emit_filters_changed)

    # ------------------------------------------------------------------
    # Signal emission
    # ------------------------------------------------------------------

    def _emit_filters_changed(self) -> None:
        self.filters_changed.emit(
            self._btn_identical.isChecked(),
            self._btn_different.isChecked(),
            self._btn_left_only.isChecked(),
            self._btn_right_only.isChecked(),
            self._search_edit.text(),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def show_identical(self) -> bool:
        return self._btn_identical.isChecked()

    @show_identical.setter
    def show_identical(self, value: bool) -> None:
        self._btn_identical.setChecked(value)

    @property
    def show_different(self) -> bool:
        return self._btn_different.isChecked()

    @show_different.setter
    def show_different(self, value: bool) -> None:
        self._btn_different.setChecked(value)

    @property
    def show_left_only(self) -> bool:
        return self._btn_left_only.isChecked()

    @show_left_only.setter
    def show_left_only(self, value: bool) -> None:
        self._btn_left_only.setChecked(value)

    @property
    def show_right_only(self) -> bool:
        return self._btn_right_only.isChecked()

    @show_right_only.setter
    def show_right_only(self, value: bool) -> None:
        self._btn_right_only.setChecked(value)

    @property
    def search_text(self) -> str:
        return self._search_edit.text()

    @search_text.setter
    def search_text(self, value: str) -> None:
        self._search_edit.setText(value)
