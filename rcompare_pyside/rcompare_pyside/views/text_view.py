"""Side-by-side text diff view."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton,
    QFileDialog,
)

from ..widgets.diff_text_edit import DiffTextEdit
from ..utils.cli_bridge import CliBridge, TextDiffReport, TextDiffLine


# Colors for diff lines
COLOR_EQUAL = QColor("#ffffff")
COLOR_INSERT = QColor("#e8f4ea")  # Light green - added on right
COLOR_DELETE = QColor("#ffe1e1")  # Light red - deleted from left
COLOR_GAP = QColor("#f5f5f5")    # Gray for gap lines


class TextView(QWidget):
    """Side-by-side text diff view with synchronized scrolling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._left_path = ""
        self._right_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Path headers
        header = QHBoxLayout()
        header.setSpacing(4)

        self._left_path_label = QLabel("Left file")
        self._left_path_label.setStyleSheet("font-weight: bold; color: #3875c4; padding: 2px 6px;")
        self._left_browse = QPushButton("Browse")
        self._left_browse.setFixedWidth(60)
        self._left_browse.clicked.connect(self._browse_left)

        self._right_path_label = QLabel("Right file")
        self._right_path_label.setStyleSheet("font-weight: bold; color: #b04552; padding: 2px 6px;")
        self._right_browse = QPushButton("Browse")
        self._right_browse.setFixedWidth(60)
        self._right_browse.clicked.connect(self._browse_right)

        left_header = QHBoxLayout()
        left_header.addWidget(self._left_path_label, 1)
        left_header.addWidget(self._left_browse)

        right_header = QHBoxLayout()
        right_header.addWidget(self._right_path_label, 1)
        right_header.addWidget(self._right_browse)

        header.addLayout(left_header, 1)
        header.addLayout(right_header, 1)
        layout.addLayout(header)

        # Splitter with two editors
        self._splitter = QSplitter(Qt.Horizontal)
        self._left_editor = DiffTextEdit()
        self._right_editor = DiffTextEdit()
        self._splitter.addWidget(self._left_editor)
        self._splitter.addWidget(self._right_editor)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        layout.addWidget(self._splitter, 1)

        # Synchronized scrolling
        self._left_editor.scroll_value_changed.connect(self._on_left_scroll)
        self._right_editor.scroll_value_changed.connect(self._on_right_scroll)

    def _on_left_scroll(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        left_max = self._left_editor.verticalScrollBar().maximum()
        right_max = self._right_editor.verticalScrollBar().maximum()
        if left_max > 0:
            ratio = value / left_max
            self._right_editor.verticalScrollBar().setValue(int(ratio * right_max))
        else:
            self._right_editor.verticalScrollBar().setValue(value)
        self._syncing = False

    def _on_right_scroll(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        left_max = self._left_editor.verticalScrollBar().maximum()
        right_max = self._right_editor.verticalScrollBar().maximum()
        if right_max > 0:
            ratio = value / right_max
            self._left_editor.verticalScrollBar().setValue(int(ratio * left_max))
        else:
            self._left_editor.verticalScrollBar().setValue(value)
        self._syncing = False

    def compare_files(self, left_path: str, right_path: str) -> None:
        """Compare two text files using Python difflib."""
        import difflib

        self._left_path = left_path
        self._right_path = right_path
        self._left_path_label.setText(left_path)
        self._right_path_label.setText(right_path)

        try:
            left_text = Path(left_path).read_text(errors="replace")
            right_text = Path(right_path).read_text(errors="replace")
        except OSError as e:
            self._left_editor.setPlainText(f"Error reading file: {e}")
            return

        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()

        # Generate side-by-side diff
        matcher = difflib.SequenceMatcher(None, left_lines, right_lines)

        display_left: list[str] = []
        display_right: list[str] = []
        colors_left: list[QColor] = []
        colors_right: list[QColor] = []
        nums_left: list[str] = []
        nums_right: list[str] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    display_left.append(left_lines[i])
                    display_right.append(right_lines[j])
                    colors_left.append(COLOR_EQUAL)
                    colors_right.append(COLOR_EQUAL)
                    nums_left.append(str(i + 1))
                    nums_right.append(str(j + 1))
            elif tag == "replace":
                max_len = max(i2 - i1, j2 - j1)
                for k in range(max_len):
                    if i1 + k < i2:
                        display_left.append(left_lines[i1 + k])
                        colors_left.append(COLOR_DELETE)
                        nums_left.append(str(i1 + k + 1))
                    else:
                        display_left.append("")
                        colors_left.append(COLOR_GAP)
                        nums_left.append("")
                    if j1 + k < j2:
                        display_right.append(right_lines[j1 + k])
                        colors_right.append(COLOR_INSERT)
                        nums_right.append(str(j1 + k + 1))
                    else:
                        display_right.append("")
                        colors_right.append(COLOR_GAP)
                        nums_right.append("")
            elif tag == "delete":
                for i in range(i1, i2):
                    display_left.append(left_lines[i])
                    display_right.append("")
                    colors_left.append(COLOR_DELETE)
                    colors_right.append(COLOR_GAP)
                    nums_left.append(str(i + 1))
                    nums_right.append("")
            elif tag == "insert":
                for j in range(j1, j2):
                    display_left.append("")
                    display_right.append(right_lines[j])
                    colors_left.append(COLOR_GAP)
                    colors_right.append(COLOR_INSERT)
                    nums_left.append("")
                    nums_right.append(str(j + 1))

        self._left_editor.set_content(display_left, colors_left, nums_left)
        self._right_editor.set_content(display_right, colors_right, nums_right)

    def load_from_cli_report(self, report: TextDiffReport, left_root: str, right_root: str) -> None:
        """Load text diff from CLI JSON output."""
        self._left_path = str(Path(left_root) / report.path)
        self._right_path = str(Path(right_root) / report.path)
        self._left_path_label.setText(self._left_path)
        self._right_path_label.setText(self._right_path)

        display_left: list[str] = []
        display_right: list[str] = []
        colors_left: list[QColor] = []
        colors_right: list[QColor] = []
        nums_left: list[str] = []
        nums_right: list[str] = []

        for line in report.lines:
            if line.change_type == "Equal":
                display_left.append(line.content)
                display_right.append(line.content)
                colors_left.append(COLOR_EQUAL)
                colors_right.append(COLOR_EQUAL)
                nums_left.append(str(line.line_number_left) if line.line_number_left else "")
                nums_right.append(str(line.line_number_right) if line.line_number_right else "")
            elif line.change_type == "Delete":
                display_left.append(line.content)
                display_right.append("")
                colors_left.append(COLOR_DELETE)
                colors_right.append(COLOR_GAP)
                nums_left.append(str(line.line_number_left) if line.line_number_left else "")
                nums_right.append("")
            elif line.change_type == "Insert":
                display_left.append("")
                display_right.append(line.content)
                colors_left.append(COLOR_GAP)
                colors_right.append(COLOR_INSERT)
                nums_left.append("")
                nums_right.append(str(line.line_number_right) if line.line_number_right else "")

        self._left_editor.set_content(display_left, colors_left, nums_left)
        self._right_editor.set_content(display_right, colors_right, nums_right)

    def clear_content(self) -> None:
        self._left_editor.clear_content()
        self._right_editor.clear_content()
        self._left_path_label.setText("Left file")
        self._right_path_label.setText("Right file")

    def _browse_left(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Left File")
        if path:
            self._left_path = path
            self._left_path_label.setText(path)
            if self._right_path:
                self.compare_files(self._left_path, self._right_path)

    def _browse_right(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Right File")
        if path:
            self._right_path = path
            self._right_path_label.setText(path)
            if self._left_path:
                self.compare_files(self._left_path, self._right_path)
