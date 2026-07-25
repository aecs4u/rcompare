"""Side-by-side text diff view."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QFileDialog, QMessageBox,
)

from ..widgets.diff_text_edit import DiffTextEdit, CharHighlights
from ..widgets.diff_overview_bar import DiffOverviewBar
from ..utils.cli_bridge import CliBridge, TextDiffReport, TextDiffLine
from ..workers.function_worker import FunctionWorker


# Default colors for diff lines
_DEFAULT_COLORS = {
    "color_added": "#c8e6c9",
    "color_removed": "#ffcdd2",
    "color_changed": "#fff9c4",
    "color_applied": "#e0e0e0",
}

COLOR_INSERT = QColor(_DEFAULT_COLORS["color_added"])
COLOR_DELETE = QColor(_DEFAULT_COLORS["color_removed"])
COLOR_GAP = QColor("#f5f5f5")

# Darker shades for intra-line (character-level) highlights
COLOR_CHAR_INSERT = QColor("#81c784")   # darker green
COLOR_CHAR_DELETE = QColor("#e57373")   # darker red


def _color_equal() -> QColor:
    """Return the 'equal' background — uses palette base for theme awareness."""
    app = QApplication.instance()
    if app:
        return app.palette().color(QPalette.ColorRole.Base)
    return QColor("#ffffff")


def _char_highlights(
    left_line: str, right_line: str
) -> tuple[list[tuple[int, int, QColor]], list[tuple[int, int, QColor]]]:
    """Compute character-level diff highlights for a pair of changed lines.

    Pure function (no Qt widget access) so it can run on a worker thread.
    """
    char_matcher = difflib.SequenceMatcher(None, left_line, right_line)
    left_hl: list[tuple[int, int, QColor]] = []
    right_hl: list[tuple[int, int, QColor]] = []
    for op, a1, a2, b1, b2 in char_matcher.get_opcodes():
        if op == "replace":
            left_hl.append((a1, a2, COLOR_CHAR_DELETE))
            right_hl.append((b1, b2, COLOR_CHAR_INSERT))
        elif op == "delete":
            left_hl.append((a1, a2, COLOR_CHAR_DELETE))
        elif op == "insert":
            right_hl.append((b1, b2, COLOR_CHAR_INSERT))
    return left_hl, right_hl


@dataclass
class _FileDiffResult:
    """Result of a background file-load + difflib computation."""

    display_left: list[str] = field(default_factory=list)
    display_right: list[str] = field(default_factory=list)
    colors_left: list[QColor] = field(default_factory=list)
    colors_right: list[QColor] = field(default_factory=list)
    nums_left: list[str] = field(default_factory=list)
    nums_right: list[str] = field(default_factory=list)
    char_hl_left: CharHighlights = field(default_factory=list)
    char_hl_right: CharHighlights = field(default_factory=list)


def _compute_file_diff(left_path: str, right_path: str, color_equal: QColor) -> _FileDiffResult:
    """Read both files and compute the side-by-side diff (runs off the GUI thread).

    Raises ``OSError`` if either file can't be read; the caller (FunctionWorker)
    turns that into an ``error`` signal.
    """
    left_text = Path(left_path).read_text(errors="replace")
    right_text = Path(right_path).read_text(errors="replace")

    left_lines = left_text.splitlines()
    right_lines = right_text.splitlines()

    matcher = difflib.SequenceMatcher(None, left_lines, right_lines)
    result = _FileDiffResult()

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                result.display_left.append(left_lines[i])
                result.display_right.append(right_lines[j])
                result.colors_left.append(color_equal)
                result.colors_right.append(color_equal)
                result.nums_left.append(str(i + 1))
                result.nums_right.append(str(j + 1))
                result.char_hl_left.append([])
                result.char_hl_right.append([])
        elif tag == "replace":
            max_len = max(i2 - i1, j2 - j1)
            for k in range(max_len):
                has_left = i1 + k < i2
                has_right = j1 + k < j2

                l_line = left_lines[i1 + k] if has_left else ""
                r_line = right_lines[j1 + k] if has_right else ""

                result.display_left.append(l_line)
                result.display_right.append(r_line)
                result.colors_left.append(COLOR_DELETE if has_left else COLOR_GAP)
                result.colors_right.append(COLOR_INSERT if has_right else COLOR_GAP)
                result.nums_left.append(str(i1 + k + 1) if has_left else "")
                result.nums_right.append(str(j1 + k + 1) if has_right else "")

                if has_left and has_right:
                    l_hl, r_hl = _char_highlights(l_line, r_line)
                    result.char_hl_left.append(l_hl)
                    result.char_hl_right.append(r_hl)
                else:
                    result.char_hl_left.append([])
                    result.char_hl_right.append([])
        elif tag == "delete":
            for i in range(i1, i2):
                result.display_left.append(left_lines[i])
                result.display_right.append("")
                result.colors_left.append(COLOR_DELETE)
                result.colors_right.append(COLOR_GAP)
                result.nums_left.append(str(i + 1))
                result.nums_right.append("")
                result.char_hl_left.append([])
                result.char_hl_right.append([])
        elif tag == "insert":
            for j in range(j1, j2):
                result.display_left.append("")
                result.display_right.append(right_lines[j])
                result.colors_left.append(COLOR_GAP)
                result.colors_right.append(COLOR_INSERT)
                result.nums_left.append("")
                result.nums_right.append(str(j + 1))
                result.char_hl_left.append([])
                result.char_hl_right.append([])

    return result


class TextView(QWidget):
    """Side-by-side text diff view with synchronized scrolling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._left_path = ""
        self._right_path = ""
        self._edit_mode = False
        self._pending_diff_paths: tuple[str, str] | None = None
        self._diff_worker: FunctionWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Path headers with edit/save controls
        header = QHBoxLayout()
        header.setSpacing(4)

        self._left_path_label = QLabel("Left file")
        self._left_path_label.setObjectName("leftPathLabel")
        self._left_path_label.setStyleSheet(
            "QLabel#leftPathLabel { font-weight: bold; color: palette(link); padding: 2px 6px; }"
        )
        self._left_browse = QPushButton("Browse")
        self._left_browse.setFixedWidth(60)
        self._left_browse.clicked.connect(self._browse_left)

        self._right_path_label = QLabel("Right file")
        self._right_path_label.setObjectName("rightPathLabel")
        self._right_path_label.setStyleSheet(
            "QLabel#rightPathLabel { font-weight: bold; color: palette(highlight); padding: 2px 6px; }"
        )
        self._right_browse = QPushButton("Browse")
        self._right_browse.setFixedWidth(60)
        self._right_browse.clicked.connect(self._browse_right)

        # Edit mode controls
        self._edit_toggle = QPushButton("Edit")
        self._edit_toggle.setFixedWidth(50)
        self._edit_toggle.setCheckable(True)
        self._edit_toggle.setToolTip("Toggle inline editing mode")
        self._edit_toggle.toggled.connect(self._on_edit_toggled)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(50)
        self._save_btn.setToolTip("Save modified files (Ctrl+S)")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)

        self._modified_label = QLabel("")
        self._modified_label.setStyleSheet("QLabel { color: #e65100; font-weight: bold; }")

        left_header = QHBoxLayout()
        left_header.addWidget(self._left_path_label, 1)
        left_header.addWidget(self._left_browse)

        right_header = QHBoxLayout()
        right_header.addWidget(self._right_path_label, 1)
        right_header.addWidget(self._right_browse)

        header.addLayout(left_header, 1)
        header.addWidget(self._edit_toggle)
        header.addWidget(self._save_btn)
        header.addWidget(self._modified_label)
        header.addLayout(right_header, 1)
        layout.addLayout(header)

        # Splitter with two editors + overview bars
        self._splitter = QSplitter(Qt.Horizontal)

        self._left_editor = DiffTextEdit()
        self._left_overview = DiffOverviewBar()
        left_pane = QWidget()
        left_lay = QHBoxLayout(left_pane)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)
        left_lay.addWidget(self._left_editor, 1)
        left_lay.addWidget(self._left_overview)

        self._right_editor = DiffTextEdit()
        self._right_overview = DiffOverviewBar()
        right_pane = QWidget()
        right_lay = QHBoxLayout(right_pane)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        right_lay.addWidget(self._right_editor, 1)
        right_lay.addWidget(self._right_overview)

        self._splitter.addWidget(left_pane)
        self._splitter.addWidget(right_pane)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)
        layout.addWidget(self._splitter, 1)

        # Overview bar click -> scroll editor
        self._left_overview.position_clicked.connect(self._on_left_overview_click)
        self._right_overview.position_clicked.connect(self._on_right_overview_click)

        # Synchronized scrolling
        self._left_editor.scroll_value_changed.connect(self._on_left_scroll)
        self._right_editor.scroll_value_changed.connect(self._on_right_scroll)

        # Debounced live re-diff timer
        self._rediff_timer = QTimer(self)
        self._rediff_timer.setSingleShot(True)
        self._rediff_timer.setInterval(300)
        self._rediff_timer.timeout.connect(self._live_rediff)

        self._left_editor.content_changed.connect(self._schedule_rediff)
        self._right_editor.content_changed.connect(self._schedule_rediff)

    def apply_appearance(self, appearance: dict) -> None:
        """Apply appearance settings (colors, font, tab width) from config."""
        global COLOR_INSERT, COLOR_DELETE
        if "color_added" in appearance:
            COLOR_INSERT = QColor(appearance["color_added"])
        if "color_removed" in appearance:
            COLOR_DELETE = QColor(appearance["color_removed"])

        from PySide6.QtGui import QFont, QFontMetricsF
        font_family = appearance.get("font_family")
        font_size = appearance.get("font_size", 10)
        tab_width = appearance.get("tab_width", 4)

        for editor in (self._left_editor, self._right_editor):
            if font_family:
                font = QFont(font_family, int(font_size))
            else:
                font = editor.font()
                font.setPointSize(int(font_size))
            editor.setFont(font)
            editor.setTabStopDistance(
                QFontMetricsF(font).horizontalAdvance(" ") * int(tab_width)
            )

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

    @staticmethod
    def _compute_char_highlights(
        left_line: str, right_line: str
    ) -> tuple[list[tuple[int, int, QColor]], list[tuple[int, int, QColor]]]:
        """Compute character-level diff highlights for a pair of changed lines."""
        return _char_highlights(left_line, right_line)

    def compare_files(self, left_path: str, right_path: str) -> None:
        """Compare two text files using Python difflib.

        File reads and the difflib computation run on a background thread
        (:class:`FunctionWorker`) so large files don't block the GUI.
        """
        self._left_path = left_path
        self._right_path = right_path
        self._left_path_label.setText(left_path)
        self._right_path_label.setText(right_path)
        self._pending_diff_paths = (left_path, right_path)

        worker = FunctionWorker(_compute_file_diff, left_path, right_path, _color_equal(), parent=self)
        worker.finished_with_result.connect(
            lambda result, lp=left_path, rp=right_path: self._on_file_diff_computed(lp, rp, result)
        )
        worker.error.connect(
            lambda msg, lp=left_path, rp=right_path: self._on_file_diff_error(lp, rp, msg)
        )
        worker.finished.connect(worker.deleteLater)
        self._diff_worker = worker
        worker.start()

    def _on_file_diff_computed(self, left_path: str, right_path: str, result: _FileDiffResult) -> None:
        """Apply a background diff computation, if it's still the active request."""
        if self._pending_diff_paths != (left_path, right_path):
            return  # a newer compare_files() call superseded this one
        self._left_editor.set_content(
            result.display_left, result.colors_left, result.nums_left, result.char_hl_left
        )
        self._right_editor.set_content(
            result.display_right, result.colors_right, result.nums_right, result.char_hl_right
        )
        self._update_overview_bars(result.colors_left, result.colors_right)

    def _on_file_diff_error(self, left_path: str, right_path: str, message: str) -> None:
        if self._pending_diff_paths != (left_path, right_path):
            return
        self._left_editor.setPlainText(f"Error reading file: {message}")

    @staticmethod
    def _parse_cli_segments(segments: list[dict], color: QColor) -> list[tuple[int, int, QColor]]:
        """Convert CLI highlighted_segments dicts to char highlight tuples."""
        result: list[tuple[int, int, QColor]] = []
        for seg in segments:
            start = seg.get("start", 0)
            end = seg.get("end", start)
            if end > start:
                result.append((start, end, color))
        return result

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
        char_hl_left: CharHighlights = []
        char_hl_right: CharHighlights = []

        for line in report.lines:
            if line.change_type == "Equal":
                display_left.append(line.content)
                display_right.append(line.content)
                colors_left.append(_color_equal())
                colors_right.append(_color_equal())
                nums_left.append(str(line.line_number_left) if line.line_number_left else "")
                nums_right.append(str(line.line_number_right) if line.line_number_right else "")
                char_hl_left.append([])
                char_hl_right.append([])
            elif line.change_type == "Delete":
                display_left.append(line.content)
                display_right.append("")
                colors_left.append(COLOR_DELETE)
                colors_right.append(COLOR_GAP)
                nums_left.append(str(line.line_number_left) if line.line_number_left else "")
                nums_right.append("")
                # Use CLI-provided segments for the deleted side
                char_hl_left.append(
                    self._parse_cli_segments(line.highlighted_segments, COLOR_CHAR_DELETE)
                )
                char_hl_right.append([])
            elif line.change_type == "Insert":
                display_left.append("")
                display_right.append(line.content)
                colors_left.append(COLOR_GAP)
                colors_right.append(COLOR_INSERT)
                nums_left.append("")
                nums_right.append(str(line.line_number_right) if line.line_number_right else "")
                char_hl_left.append([])
                char_hl_right.append(
                    self._parse_cli_segments(line.highlighted_segments, COLOR_CHAR_INSERT)
                )

        self._left_editor.set_content(display_left, colors_left, nums_left, char_hl_left)
        self._right_editor.set_content(display_right, colors_right, nums_right, char_hl_right)
        self._update_overview_bars(colors_left, colors_right)

    def show_diff_text(self, content: str, title: str = "Diff") -> None:
        """Display raw diff/patch text content in the left editor."""
        self._left_path_label.setText(title)
        self._right_path_label.setText("")

        lines = content.splitlines()
        display: list[str] = []
        colors: list[QColor] = []
        nums: list[str] = []

        for i, line in enumerate(lines, 1):
            display.append(line)
            nums.append(str(i))
            if line.startswith("+") and not line.startswith("+++"):
                colors.append(COLOR_INSERT)
            elif line.startswith("-") and not line.startswith("---"):
                colors.append(COLOR_DELETE)
            elif line.startswith("@@"):
                colors.append(QColor("#e0e0ff"))
            else:
                colors.append(_color_equal())

        self._left_editor.set_content(display, colors, nums)
        self._right_editor.clear_content()

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

    # ------------------------------------------------------------------
    # Inline editing
    # ------------------------------------------------------------------

    def _on_edit_toggled(self, checked: bool) -> None:
        """Toggle inline editing mode."""
        self._edit_mode = checked
        self._left_editor.set_editable(checked)
        self._right_editor.set_editable(checked)
        self._edit_toggle.setText("View" if checked else "Edit")
        if not checked:
            self._modified_label.setText("")
            self._save_btn.setEnabled(False)

    def _schedule_rediff(self) -> None:
        """Schedule a debounced live re-diff."""
        if not self._edit_mode:
            return
        self._modified_label.setText("Modified")
        self._save_btn.setEnabled(True)
        self._rediff_timer.start()

    def _live_rediff(self) -> None:
        """Re-compute the diff from the current editor contents without changing text."""
        import difflib

        left_lines = self._left_editor.get_lines()
        right_lines = self._right_editor.get_lines()

        matcher = difflib.SequenceMatcher(None, left_lines, right_lines)

        colors_left: list[QColor] = []
        colors_right: list[QColor] = []
        char_hl_left: CharHighlights = []
        char_hl_right: CharHighlights = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                count = i2 - i1
                colors_left.extend([_color_equal()] * count)
                colors_right.extend([_color_equal()] * count)
                char_hl_left.extend([[]] * count)
                char_hl_right.extend([[]] * count)
            elif tag == "replace":
                max_len = max(i2 - i1, j2 - j1)
                for k in range(max_len):
                    has_left = i1 + k < i2
                    has_right = j1 + k < j2
                    colors_left.append(COLOR_DELETE if has_left else COLOR_GAP)
                    colors_right.append(COLOR_INSERT if has_right else COLOR_GAP)
                    if has_left and has_right:
                        l_hl, r_hl = self._compute_char_highlights(
                            left_lines[i1 + k], right_lines[j1 + k]
                        )
                        char_hl_left.append(l_hl)
                        char_hl_right.append(r_hl)
                    else:
                        char_hl_left.append([])
                        char_hl_right.append([])
            elif tag == "delete":
                count = i2 - i1
                colors_left.extend([COLOR_DELETE] * count)
                colors_right.extend([COLOR_GAP] * count)
                char_hl_left.extend([[]] * count)
                char_hl_right.extend([[]] * count)
            elif tag == "insert":
                count = j2 - j1
                colors_left.extend([COLOR_GAP] * count)
                colors_right.extend([COLOR_INSERT] * count)
                char_hl_left.extend([[]] * count)
                char_hl_right.extend([[]] * count)

        # Update colors without changing text content
        self._left_editor._line_colors = colors_left
        self._left_editor._char_highlights = char_hl_left
        self._right_editor._line_colors = colors_right
        self._right_editor._char_highlights = char_hl_right
        self._left_editor.viewport().update()
        self._right_editor.viewport().update()

    def _on_save(self) -> None:
        """Save modified content back to disk."""
        saved = []
        if self._left_editor.dirty and self._left_path:
            try:
                Path(self._left_path).write_text(
                    self._left_editor.toPlainText(), encoding="utf-8",
                )
                self._left_editor._dirty = False
                saved.append("left")
            except OSError as exc:
                QMessageBox.critical(self, "Save Failed", f"Left file: {exc}")
                return

        if self._right_editor.dirty and self._right_path:
            try:
                Path(self._right_path).write_text(
                    self._right_editor.toPlainText(), encoding="utf-8",
                )
                self._right_editor._dirty = False
                saved.append("right")
            except OSError as exc:
                QMessageBox.critical(self, "Save Failed", f"Right file: {exc}")
                return

        if saved:
            self._modified_label.setText("Saved")
            self._save_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Overview bar integration
    # ------------------------------------------------------------------

    def _update_overview_bars(self, colors_left: list[QColor], colors_right: list[QColor]) -> None:
        """Update the overview bars with the current diff colors."""
        base = _color_equal()
        left_entries = [
            (i, c) for i, c in enumerate(colors_left) if c.isValid() and c != base
        ]
        right_entries = [
            (i, c) for i, c in enumerate(colors_right) if c.isValid() and c != base
        ]
        self._left_overview.set_entries(left_entries, len(colors_left))
        self._right_overview.set_entries(right_entries, len(colors_right))

    def _on_left_overview_click(self, ratio: float) -> None:
        """Scroll left editor to the clicked position."""
        sb = self._left_editor.verticalScrollBar()
        sb.setValue(int(ratio * sb.maximum()))

    def _on_right_overview_click(self, ratio: float) -> None:
        """Scroll right editor to the clicked position."""
        sb = self._right_editor.verticalScrollBar()
        sb.setValue(int(ratio * sb.maximum()))
