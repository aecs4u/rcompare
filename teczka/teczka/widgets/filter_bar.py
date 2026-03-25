"""FilterBar widget providing toggle buttons and a search field for result filtering."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

# Indicator colors for diff status (semantic colors, kept for clarity)
# These could be themed in the future via a color scheme system
COLOR_IDENTICAL = "#4caf50"
COLOR_DIFFERENT = "#e05a5a"
COLOR_LEFT_ONLY = "#5b85dd"
COLOR_RIGHT_ONLY = "#d85a6a"
COLOR_FILES_ONLY = "#6d96d6"

# KDE Compliance: Simplified button style using palette colors where possible
_BUTTON_STYLE_TEMPLATE = """
QToolButton {{
    border: 1px solid palette(mid);
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 12px;
    background-color: palette(button);
    color: palette(button-text);
}}
QToolButton:checked {{
    border: 2px solid {color};
    background-color: {color_bg};
    color: palette(bright-text);
    font-weight: bold;
}}
QToolButton:hover {{
    background-color: palette(light);
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

    # (show_identical, show_different, show_left_only, show_right_only, show_files_only, search_text)
    filters_changed = Signal(bool, bool, bool, bool, bool, str)
    diff_option_changed = Signal(str)

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
        self._btn_files_only = _make_toggle("Files Only", COLOR_FILES_ONLY, checked=False)

        layout.addWidget(self._btn_identical)
        layout.addWidget(self._btn_different)
        layout.addWidget(self._btn_left_only)
        layout.addWidget(self._btn_right_only)
        layout.addWidget(self._btn_files_only)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # --- Diff options combo (inspired by classic compare tools) ---
        self._diff_options_label = QLabel("Diffs:")
        self._diff_options = QComboBox()
        self._diff_options.setMinimumWidth(280)
        self._diff_options.addItem("Show Differences", "show_differences")
        self._diff_options.addItem("Show No Orphans", "show_no_orphans")
        self._diff_options.addItem(
            "Show Differences but No Orphans",
            "show_differences_no_orphans",
        )
        self._diff_options.addItem("Show Orphans", "show_orphans")
        self._diff_options.addItem("Show Left Newer", "show_left_newer")
        self._diff_options.addItem("Show Right Newer", "show_right_newer")
        self._diff_options.addItem(
            "Show Left Newer and Left Orphans",
            "show_left_newer_left_orphans",
        )
        self._diff_options.addItem(
            "Show Right Newer and Right Orphans",
            "show_right_newer_right_orphans",
        )
        self._diff_options.addItem("Show Left Orphans", "show_left_orphans")
        self._diff_options.addItem("Show Right Orphans", "show_right_orphans")

        layout.addWidget(self._diff_options_label)
        layout.addWidget(self._diff_options)

        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator2)

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
        self._btn_files_only.toggled.connect(self._emit_filters_changed)
        self._search_edit.textChanged.connect(self._emit_filters_changed)
        self._diff_options.currentIndexChanged.connect(self._on_diff_option_changed)

    # ------------------------------------------------------------------
    # Signal emission
    # ------------------------------------------------------------------

    def _emit_filters_changed(self) -> None:
        self.filters_changed.emit(
            self._btn_identical.isChecked(),
            self._btn_different.isChecked(),
            self._btn_left_only.isChecked(),
            self._btn_right_only.isChecked(),
            self._btn_files_only.isChecked(),
            self._search_edit.text(),
        )

    def _on_diff_option_changed(self) -> None:
        self.diff_option_changed.emit(self.diff_option_mode)

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
    def show_files_only(self) -> bool:
        return self._btn_files_only.isChecked()

    @show_files_only.setter
    def show_files_only(self, value: bool) -> None:
        self._btn_files_only.setChecked(value)

    @property
    def search_text(self) -> str:
        return self._search_edit.text()

    @search_text.setter
    def search_text(self, value: str) -> None:
        self._search_edit.setText(value)

    @property
    def diff_option_mode(self) -> str:
        data = self._diff_options.currentData()
        return str(data) if isinstance(data, str) else "show_differences"

    @diff_option_mode.setter
    def diff_option_mode(self, value: str) -> None:
        idx = self._diff_options.findData(value)
        if idx < 0:
            idx = 0
        self._diff_options.setCurrentIndex(idx)

    def focus_search(self) -> None:
        self._search_edit.setFocus()
        self._search_edit.selectAll()

    def clear_search(self) -> None:
        self._search_edit.clear()
