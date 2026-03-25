"""Live palette management for teczka.

Connects to QApplication.paletteChanged to refresh UI components
when the system theme changes (e.g., KDE dark/light toggle).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


class PaletteManager(QObject):
    """Monitors system palette changes and provides theme-aware colors."""

    palette_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dark = False
        app = QApplication.instance()
        if app:
            app.paletteChanged.connect(self._on_palette_changed)
            self._detect_theme()

    def _on_palette_changed(self, palette: QPalette) -> None:
        self._detect_theme()
        self.palette_changed.emit()

    def _detect_theme(self) -> None:
        """Detect dark/light theme from window background lightness."""
        palette = QApplication.palette()
        bg = palette.color(QPalette.ColorRole.Window)
        self._dark = bg.lightnessF() < 0.5

    @property
    def is_dark(self) -> bool:
        return self._dark

    @property
    def color_identical(self) -> QColor:
        return QColor("#2d5a2d") if self._dark else QColor("#c8e6c9")

    @property
    def color_different(self) -> QColor:
        return QColor("#8b2252") if self._dark else QColor("#ffcdd2")

    @property
    def color_added(self) -> QColor:
        return QColor("#1a5276") if self._dark else QColor("#bbdefb")

    @property
    def color_left_only(self) -> QColor:
        return QColor("#7d6608") if self._dark else QColor("#fff9c4")

    @property
    def color_right_only(self) -> QColor:
        return QColor("#4a235a") if self._dark else QColor("#e1bee7")

    @property
    def color_gap(self) -> QColor:
        return QColor("#555555") if self._dark else QColor("#e0e0e0")

    @property
    def color_conflict(self) -> QColor:
        return QColor("#b71c1c") if self._dark else QColor("#ef9a9a")

    def diff_colors(self) -> dict[str, QColor]:
        """Return all diff colors as a dict for easy iteration."""
        return {
            "identical": self.color_identical,
            "different": self.color_different,
            "added": self.color_added,
            "left_only": self.color_left_only,
            "right_only": self.color_right_only,
            "gap": self.color_gap,
            "conflict": self.color_conflict,
        }
