"""Custom text editor widget for displaying one side of a diff."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QTextFormat, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit


class LineNumberArea(QWidget):
    """Line number gutter for DiffTextEdit."""

    def __init__(self, editor: DiffTextEdit):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self._editor.paint_line_numbers(event)


class DiffTextEdit(QPlainTextEdit):
    """QPlainTextEdit with line numbers and per-line background coloring.

    Used for displaying one side of a text diff.
    """

    scroll_value_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setWordWrapMode(0)  # QTextOption.NoWrap
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        self._line_number_area = LineNumberArea(self)
        self._line_colors: list[QColor] = []
        self._line_numbers: list[str] = []  # Custom line numbers (can be empty for gaps)

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)

        self.verticalScrollBar().valueChanged.connect(self.scroll_value_changed.emit)

        self._update_line_number_area_width(0)

    def set_content(self, lines: list[str], colors: list[QColor], line_numbers: list[str]) -> None:
        """Set the diff content with per-line colors and custom line numbers."""
        self._line_colors = colors
        self._line_numbers = line_numbers
        self.setPlainText("\n".join(lines))
        self.viewport().update()

    def clear_content(self) -> None:
        """Clear all content."""
        self._line_colors = []
        self._line_numbers = []
        self.clear()

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        # Also consider custom line numbers width
        if self._line_numbers:
            max_num = max((len(n) for n in self._line_numbers if n), default=digits)
            digits = max(digits, max_num)
        space = 10 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def _update_line_number_area_width(self, _: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event: QPaintEvent) -> None:
        """Paint line numbers in the gutter area."""
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#f0f0f0"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # Draw line background color if we have one
                if block_number < len(self._line_colors):
                    bg = self._line_colors[block_number]
                    if bg.isValid() and bg != QColor(Qt.white):
                        painter.fillRect(
                            0, top,
                            self._line_number_area.width(),
                            round(self.blockBoundingRect(block).height()),
                            bg,
                        )

                # Draw line number
                if block_number < len(self._line_numbers):
                    number = self._line_numbers[block_number]
                else:
                    number = str(block_number + 1)

                if number:
                    painter.setPen(QColor("#808080"))
                    painter.drawText(
                        0, top,
                        self._line_number_area.width() - 4,
                        round(self.blockBoundingRect(block).height()),
                        Qt.AlignRight | Qt.AlignVCenter,
                        number,
                    )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint line backgrounds before the text."""
        # Paint line background colors on the viewport
        painter = QPainter(self.viewport())
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                height = round(self.blockBoundingRect(block).height())
                if block_number < len(self._line_colors):
                    bg = self._line_colors[block_number]
                    if bg.isValid() and bg != QColor(Qt.white):
                        painter.fillRect(
                            0, top, self.viewport().width(), height, bg
                        )
                block_number += 1
                top += height
            block = block.next()

        painter.end()

        # Now paint the text on top
        super().paintEvent(event)
