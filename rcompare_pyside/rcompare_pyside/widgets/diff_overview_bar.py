"""Diff overview mini-map bar widget.

A narrow vertical bar that shows a color-coded overview of the entire diff,
similar to Beyond Compare's overview strip. Clicking scrolls the associated
view to that position.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QMouseEvent
from PySide6.QtWidgets import QWidget

_BAR_WIDTH = 24
_MARK_MIN_HEIGHT = 2


class DiffOverviewBar(QWidget):
    """Thin vertical bar painting colored marks proportional to line positions.

    Signals:
        position_clicked(float): Emitted when the user clicks or drags on the
            bar. The value is a ratio in the range 0.0 -- 1.0 representing the
            vertical position within the document.
    """

    position_clicked = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_BAR_WIDTH)

        self._entries: list[tuple[int, QColor]] = []
        self._total_lines: int = 0
        self._viewport_start: float = 0.0
        self._viewport_end: float = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_entries(self, entries: list[tuple[int, QColor]], total_lines: int) -> None:
        """Set the colored marks to display.

        Args:
            entries: List of ``(line_index, color)`` pairs.
            total_lines: Total number of lines in the document.
        """
        self._entries = entries
        self._total_lines = max(total_lines, 1)
        self.update()

    def set_viewport_range(self, start_ratio: float, end_ratio: float) -> None:
        """Update the translucent viewport indicator.

        Args:
            start_ratio: Top edge of the visible area as a 0.0 -- 1.0 ratio.
            end_ratio: Bottom edge of the visible area as a 0.0 -- 1.0 ratio.
        """
        self._viewport_start = max(0.0, min(start_ratio, 1.0))
        self._viewport_end = max(0.0, min(end_ratio, 1.0))
        self.update()

    def clear(self) -> None:
        """Remove all marks and reset the viewport indicator."""
        self._entries = []
        self._total_lines = 0
        self._viewport_start = 0.0
        self._viewport_end = 1.0
        self.update()

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_position(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._emit_position(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_position(self, event: QMouseEvent) -> None:
        h = self.height()
        if h <= 0:
            return
        ratio = max(0.0, min(event.position().y() / h, 1.0))
        self.position_clicked.emit(ratio)

    def _paint(self, painter: QPainter) -> None:
        w = self.width()
        h = self.height()

        # 1. Background ---------------------------------------------------
        bg = self.palette().alternateBase().color()
        painter.fillRect(0, 0, w, h, bg)

        if self._total_lines <= 0 or h <= 0:
            self._paint_viewport(painter, w, h)
            return

        # 2. Colored marks -------------------------------------------------
        painter.setPen(Qt.PenStyle.NoPen)
        for line_idx, color in self._entries:
            y = int(line_idx / self._total_lines * h)
            mark_h = max(_MARK_MIN_HEIGHT, int(h / self._total_lines))
            painter.fillRect(QRect(0, y, w, mark_h), color)

        # 3. Viewport indicator --------------------------------------------
        self._paint_viewport(painter, w, h)

    def _paint_viewport(self, painter: QPainter, w: int, h: int) -> None:
        y_start = int(self._viewport_start * h)
        y_end = int(self._viewport_end * h)
        vp_height = max(y_end - y_start, 1)

        overlay = self.palette().highlight().color()
        overlay.setAlpha(48)
        painter.fillRect(QRect(0, y_start, w, vp_height), overlay)

        # Draw thin border lines at top and bottom of the viewport region.
        border = self.palette().highlight().color()
        border.setAlpha(120)
        painter.setPen(border)
        painter.drawLine(0, y_start, w - 1, y_start)
        painter.drawLine(0, y_start + vp_height - 1, w - 1, y_start + vp_height - 1)
