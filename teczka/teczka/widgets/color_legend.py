"""ColorLegend widget showing colored squares with labels to explain diff view colors."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

# Default legend entries: (label, hex color)
_DEFAULT_ENTRIES: list[tuple[str, str]] = [
    ("Identical", "#c8e6c9"),
    ("Different", "#ffcdd2"),
    ("Added", "#c8e6c9"),
    ("Left Only", "#bbdefb"),
    ("Right Only", "#ffe0b2"),
    ("Gap", "#f5f5f5"),
]

_SWATCH_SIZE = 12


class ColorLegend(QWidget):
    """Compact horizontal bar displaying colored squares with descriptive labels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(24)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(4)

        self._entries: list[tuple[str, QColor]] = [
            (label, QColor(color)) for label, color in _DEFAULT_ENTRIES
        ]
        self._rebuild()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_entries(self, entries: list[tuple[str, QColor]]) -> None:
        """Replace the legend entries and rebuild the widget contents."""
        self._entries = list(entries)
        self._rebuild()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Clear the layout and recreate swatch/label pairs."""
        # Remove existing items
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        label_font = QFont()
        label_font.setPointSize(8)

        for label_text, color in self._entries:
            # Colored square
            swatch = QFrame(self)
            swatch.setFixedSize(_SWATCH_SIZE, _SWATCH_SIZE)
            swatch.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid palette(mid);"
            )
            self._layout.addWidget(swatch, alignment=Qt.AlignVCenter)

            # Descriptive label
            label = QLabel(label_text, self)
            label.setFont(label_font)
            label.setStyleSheet("color: palette(text); border: none;")
            self._layout.addWidget(label, alignment=Qt.AlignVCenter)

            # Small gap between entries
            spacer = QFrame(self)
            spacer.setFixedWidth(6)
            spacer.setStyleSheet("border: none; background: transparent;")
            self._layout.addWidget(spacer)

        # Push entries to the left
        self._layout.addStretch()
