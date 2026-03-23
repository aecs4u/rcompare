"""Three-way merge view inspired by Beyond Compare and KDiff3."""

from __future__ import annotations

import difflib
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QToolBar, QFileDialog, QMessageBox,
)

from ..widgets.diff_text_edit import DiffTextEdit


# Highlight colors for merge regions
COLOR_LEFT = QColor("#bbdefb")       # blue tint - lines from left
COLOR_RIGHT = QColor("#c8e6c9")      # green tint - lines from right
COLOR_CONFLICT = QColor("#ffcdd2")   # red tint - unresolved conflict
COLOR_RESOLVED = QColor("#e0e0e0")   # light gray - resolved


class ConflictType(Enum):
    """Type of conflict region."""
    LEFT_ONLY = "left_only"
    RIGHT_ONLY = "right_only"
    BOTH_DIFFER = "conflict"


class ConflictRegion:
    """Tracks a single conflict in the merge output."""

    __slots__ = (
        "start_line", "end_line", "conflict_type",
        "left_lines", "right_lines", "base_lines",
        "resolved",
    )

    def __init__(
        self,
        start_line: int,
        end_line: int,
        conflict_type: ConflictType,
        left_lines: list[str],
        right_lines: list[str],
        base_lines: list[str],
    ) -> None:
        self.start_line = start_line
        self.end_line = end_line
        self.conflict_type = conflict_type
        self.left_lines = left_lines
        self.right_lines = right_lines
        self.base_lines = base_lines
        self.resolved = False


class MergeView(QWidget):
    """Three-way merge view with conflict resolution.

    Layout:
        Top row (3 panes): Left (Yours) | Base (Ancestor) | Right (Theirs)
        Bottom row (1 pane): Output (Merged)
    """

    merge_saved = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._syncing = False
        self._left_path = ""
        self._base_path = ""
        self._right_path = ""

        self._conflicts: list[ConflictRegion] = []
        self._current_conflict = -1

        self._setup_ui()
        self._connect_scrolling()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # --- Toolbar ---
        toolbar = QToolBar()
        toolbar.setMovable(False)

        self._btn_prev = QPushButton("Previous Conflict")
        self._btn_prev.clicked.connect(self._go_prev_conflict)
        toolbar.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Next Conflict")
        self._btn_next.clicked.connect(self._go_next_conflict)
        toolbar.addWidget(self._btn_next)

        toolbar.addSeparator()

        self._conflict_label = QLabel("No conflicts")
        toolbar.addWidget(self._conflict_label)

        toolbar.addSeparator()

        self._btn_take_left = QPushButton("Take Left")
        self._btn_take_left.clicked.connect(self._take_left)
        toolbar.addWidget(self._btn_take_left)

        self._btn_take_right = QPushButton("Take Right")
        self._btn_take_right.clicked.connect(self._take_right)
        toolbar.addWidget(self._btn_take_right)

        self._btn_take_base = QPushButton("Take Base")
        self._btn_take_base.clicked.connect(self._take_base)
        toolbar.addWidget(self._btn_take_base)

        self._btn_take_both_lr = QPushButton("Take Both (L+R)")
        self._btn_take_both_lr.clicked.connect(self._take_both_lr)
        toolbar.addWidget(self._btn_take_both_lr)

        self._btn_take_both_rl = QPushButton("Take Both (R+L)")
        self._btn_take_both_rl.clicked.connect(self._take_both_rl)
        toolbar.addWidget(self._btn_take_both_rl)

        toolbar.addSeparator()

        self._btn_save = QPushButton("Save Merged")
        self._btn_save.clicked.connect(self._save_merged)
        toolbar.addWidget(self._btn_save)

        layout.addWidget(toolbar)

        # --- Header labels ---
        header = QHBoxLayout()
        header.setSpacing(4)

        self._left_label = QLabel("Left (Yours)")
        self._left_label.setStyleSheet("font-weight: bold; padding: 2px 6px;")
        self._base_label = QLabel("Base (Ancestor)")
        self._base_label.setStyleSheet("font-weight: bold; padding: 2px 6px;")
        self._right_label = QLabel("Right (Theirs)")
        self._right_label.setStyleSheet("font-weight: bold; padding: 2px 6px;")

        header.addWidget(self._left_label, 1)
        header.addWidget(self._base_label, 1)
        header.addWidget(self._right_label, 1)
        layout.addLayout(header)

        # --- Main vertical splitter: top (3 panes) / bottom (output) ---
        self._vsplitter = QSplitter(Qt.Orientation.Vertical)

        # Top: 3-way horizontal splitter
        self._hsplitter = QSplitter(Qt.Orientation.Horizontal)

        self._left_editor = DiffTextEdit()
        self._base_editor = DiffTextEdit()
        self._right_editor = DiffTextEdit()

        self._hsplitter.addWidget(self._left_editor)
        self._hsplitter.addWidget(self._base_editor)
        self._hsplitter.addWidget(self._right_editor)
        self._hsplitter.setStretchFactor(0, 1)
        self._hsplitter.setStretchFactor(1, 1)
        self._hsplitter.setStretchFactor(2, 1)

        self._vsplitter.addWidget(self._hsplitter)

        # Bottom: output pane with its own header
        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(2)

        self._output_label = QLabel("Output (Merged)")
        self._output_label.setStyleSheet("font-weight: bold; padding: 2px 6px;")
        output_layout.addWidget(self._output_label)

        self._output_editor = DiffTextEdit()
        self._output_editor.set_editable(True)
        output_layout.addWidget(self._output_editor, 1)

        self._vsplitter.addWidget(output_container)
        self._vsplitter.setStretchFactor(0, 2)
        self._vsplitter.setStretchFactor(1, 1)

        layout.addWidget(self._vsplitter, 1)

    def _connect_scrolling(self) -> None:
        """Wire up synchronized scrolling across all four panes."""
        self._left_editor.scroll_value_changed.connect(self._on_scroll)
        self._base_editor.scroll_value_changed.connect(self._on_scroll)
        self._right_editor.scroll_value_changed.connect(self._on_scroll)
        self._output_editor.scroll_value_changed.connect(self._on_scroll)

    def _on_scroll(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True

        sender = self.sender()
        editors = [
            self._left_editor, self._base_editor,
            self._right_editor, self._output_editor,
        ]
        sender_max = sender.verticalScrollBar().maximum() if sender else 1

        for editor in editors:
            if editor is sender:
                continue
            target_max = editor.verticalScrollBar().maximum()
            if sender_max > 0:
                ratio = value / sender_max
                editor.verticalScrollBar().setValue(int(ratio * target_max))
            else:
                editor.verticalScrollBar().setValue(value)

        self._syncing = False

    # ------------------------------------------------------------------
    # Loading and 3-way merge
    # ------------------------------------------------------------------

    def load_merge(self, left_path: str, base_path: str, right_path: str) -> None:
        """Read three files and perform a simple 3-way merge."""
        self._left_path = left_path
        self._base_path = base_path
        self._right_path = right_path

        self._left_label.setText(f"Left (Yours) - {left_path}")
        self._base_label.setText(f"Base (Ancestor) - {base_path}")
        self._right_label.setText(f"Right (Theirs) - {right_path}")

        try:
            left_lines = Path(left_path).read_text(errors="replace").splitlines()
            base_lines = Path(base_path).read_text(errors="replace").splitlines()
            right_lines = Path(right_path).read_text(errors="replace").splitlines()
        except OSError as e:
            self._output_editor.setPlainText(f"Error reading files: {e}")
            return

        self._populate_source_panes(left_lines, base_lines, right_lines)
        self._perform_merge(left_lines, base_lines, right_lines)
        self._update_conflict_label()

        if self._conflicts:
            self._current_conflict = 0
            self._scroll_to_conflict(0)

    def _populate_source_panes(
        self,
        left_lines: list[str],
        base_lines: list[str],
        right_lines: list[str],
    ) -> None:
        """Populate the three source panes with plain content."""
        white = QColor(Qt.GlobalColor.white)

        def _make_colors(n: int) -> list[QColor]:
            return [white] * n

        def _make_nums(n: int) -> list[str]:
            return [str(i + 1) for i in range(n)]

        self._left_editor.set_content(
            left_lines, _make_colors(len(left_lines)), _make_nums(len(left_lines)),
        )
        self._base_editor.set_content(
            base_lines, _make_colors(len(base_lines)), _make_nums(len(base_lines)),
        )
        self._right_editor.set_content(
            right_lines, _make_colors(len(right_lines)), _make_nums(len(right_lines)),
        )

    def _perform_merge(
        self,
        left_lines: list[str],
        base_lines: list[str],
        right_lines: list[str],
    ) -> None:
        """Simple 3-way merge using difflib.

        Algorithm:
        1. Diff left vs base and right vs base.
        2. Walk through base lines; auto-merge where only one side changed.
        3. Mark conflicts where both sides changed the same region.
        """
        left_ops = difflib.SequenceMatcher(None, base_lines, left_lines).get_opcodes()
        right_ops = difflib.SequenceMatcher(None, base_lines, right_lines).get_opcodes()

        # Build per-base-line change maps
        base_len = len(base_lines)
        # For each base line, record what left and right want to do
        # We work in terms of "chunks" aligned to the base

        output_lines: list[str] = []
        output_colors: list[QColor] = []
        self._conflicts = []

        # Convert opcodes into a base-indexed structure
        left_changes = self._opcodes_to_changes(left_ops, base_lines, left_lines)
        right_changes = self._opcodes_to_changes(right_ops, base_lines, right_lines)

        # Merge the two change lists against the base
        all_base_regions = sorted(
            set(left_changes.keys()) | set(right_changes.keys())
        )

        # Track which base regions we have processed
        next_base = 0

        for region_start in all_base_regions:
            l_change = left_changes.get(region_start)
            r_change = right_changes.get(region_start)

            # Emit any unchanged base lines before this region
            if region_start > next_base:
                for i in range(next_base, region_start):
                    if i < base_len:
                        output_lines.append(base_lines[i])
                        output_colors.append(QColor(Qt.GlobalColor.white))

            l_end = l_change[0] if l_change else region_start
            l_new = l_change[1] if l_change else []
            r_end = r_change[0] if r_change else region_start
            r_new = r_change[1] if r_change else []

            region_end = max(l_end, r_end)

            base_slice = base_lines[region_start:region_end]

            if l_change and not r_change:
                # Only left changed
                start = len(output_lines)
                for line in l_new:
                    output_lines.append(line)
                    output_colors.append(COLOR_LEFT)
                end = len(output_lines)
                if start < end:
                    self._conflicts.append(ConflictRegion(
                        start, end, ConflictType.LEFT_ONLY,
                        l_new, base_slice, base_slice,
                    ))
                    self._conflicts[-1].resolved = True
            elif r_change and not l_change:
                # Only right changed
                start = len(output_lines)
                for line in r_new:
                    output_lines.append(line)
                    output_colors.append(COLOR_RIGHT)
                end = len(output_lines)
                if start < end:
                    self._conflicts.append(ConflictRegion(
                        start, end, ConflictType.RIGHT_ONLY,
                        base_slice, base_slice, r_new,
                    ))
                    self._conflicts[-1].resolved = True
            elif l_change and r_change:
                # Both sides changed
                if l_new == r_new:
                    # Same change on both sides - auto-resolve
                    start = len(output_lines)
                    for line in l_new:
                        output_lines.append(line)
                        output_colors.append(COLOR_RESOLVED)
                    end = len(output_lines)
                    if start < end:
                        self._conflicts.append(ConflictRegion(
                            start, end, ConflictType.BOTH_DIFFER,
                            l_new, base_slice, r_new,
                        ))
                        self._conflicts[-1].resolved = True
                else:
                    # Real conflict
                    start = len(output_lines)
                    output_lines.append("<<<< CONFLICT >>>>")
                    output_colors.append(COLOR_CONFLICT)
                    for line in l_new:
                        output_lines.append(line)
                        output_colors.append(COLOR_CONFLICT)
                    output_lines.append("====")
                    output_colors.append(COLOR_CONFLICT)
                    for line in r_new:
                        output_lines.append(line)
                        output_colors.append(COLOR_CONFLICT)
                    output_lines.append("<<<< END >>>>")
                    output_colors.append(COLOR_CONFLICT)
                    end = len(output_lines)
                    self._conflicts.append(ConflictRegion(
                        start, end, ConflictType.BOTH_DIFFER,
                        l_new, base_slice, r_new,
                    ))

            next_base = region_end

        # Emit remaining base lines
        for i in range(next_base, base_len):
            output_lines.append(base_lines[i])
            output_colors.append(QColor(Qt.GlobalColor.white))

        nums = [str(i + 1) for i in range(len(output_lines))]
        self._output_editor.set_content(output_lines, output_colors, nums)

    @staticmethod
    def _opcodes_to_changes(
        opcodes: list[tuple[str, int, int, int, int]],
        base_lines: list[str],
        other_lines: list[str],
    ) -> dict[int, tuple[int, list[str]]]:
        """Convert opcodes into a dict mapping base start index to (base_end, new_lines).

        Only non-equal opcodes are included.
        """
        changes: dict[int, tuple[int, list[str]]] = {}
        for tag, b1, b2, o1, o2 in opcodes:
            if tag == "equal":
                continue
            # tag is replace, insert, or delete
            new_lines = list(other_lines[o1:o2])
            changes[b1] = (b2, new_lines)
        return changes

    # ------------------------------------------------------------------
    # Conflict navigation
    # ------------------------------------------------------------------

    def _unresolved_conflicts(self) -> list[int]:
        """Return indices of unresolved conflicts."""
        return [i for i, c in enumerate(self._conflicts) if not c.resolved]

    def _update_conflict_label(self) -> None:
        unresolved = self._unresolved_conflicts()
        total = len(self._conflicts)
        n_unresolved = len(unresolved)

        if total == 0:
            self._conflict_label.setText("No conflicts")
        elif self._current_conflict < 0 or self._current_conflict >= total:
            self._conflict_label.setText(
                f"{n_unresolved} unresolved of {total} regions"
            )
        else:
            self._conflict_label.setText(
                f"Conflict {self._current_conflict + 1} of {total}"
                f" ({n_unresolved} unresolved)"
            )

    def _go_prev_conflict(self) -> None:
        if not self._conflicts:
            return
        if self._current_conflict <= 0:
            self._current_conflict = len(self._conflicts) - 1
        else:
            self._current_conflict -= 1
        self._scroll_to_conflict(self._current_conflict)
        self._update_conflict_label()

    def _go_next_conflict(self) -> None:
        if not self._conflicts:
            return
        if self._current_conflict >= len(self._conflicts) - 1:
            self._current_conflict = 0
        else:
            self._current_conflict += 1
        self._scroll_to_conflict(self._current_conflict)
        self._update_conflict_label()

    def _scroll_to_conflict(self, index: int) -> None:
        """Scroll the output editor to make the given conflict visible."""
        if index < 0 or index >= len(self._conflicts):
            return
        conflict = self._conflicts[index]
        block = self._output_editor.document().findBlockByLineNumber(conflict.start_line)
        if block.isValid():
            cursor = self._output_editor.textCursor()
            cursor.setPosition(block.position())
            self._output_editor.setTextCursor(cursor)
            self._output_editor.centerCursor()

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def _resolve_current(self, replacement_lines: list[str]) -> None:
        """Replace the current conflict region in the output with the given lines."""
        if self._current_conflict < 0 or self._current_conflict >= len(self._conflicts):
            return

        conflict = self._conflicts[self._current_conflict]

        # Get current output lines
        all_lines = self._output_editor.toPlainText().splitlines()
        all_colors = list(self._output_editor._line_colors)

        # Ensure color list matches line count
        while len(all_colors) < len(all_lines):
            all_colors.append(QColor(Qt.GlobalColor.white))

        old_len = conflict.end_line - conflict.start_line
        new_len = len(replacement_lines)

        # Replace lines in the output
        all_lines[conflict.start_line:conflict.end_line] = replacement_lines
        all_colors[conflict.start_line:conflict.end_line] = [COLOR_RESOLVED] * new_len

        # Update the conflict as resolved
        conflict.resolved = True
        old_end = conflict.end_line
        conflict.end_line = conflict.start_line + new_len

        # Adjust subsequent conflict positions
        delta = new_len - old_len
        for c in self._conflicts[self._current_conflict + 1:]:
            c.start_line += delta
            c.end_line += delta

        # Re-populate the output editor
        nums = [str(i + 1) for i in range(len(all_lines))]
        self._output_editor.set_content(all_lines, all_colors, nums)

        self._update_conflict_label()
        self._scroll_to_conflict(self._current_conflict)

    def _take_left(self) -> None:
        if self._current_conflict < 0 or self._current_conflict >= len(self._conflicts):
            return
        self._resolve_current(list(self._conflicts[self._current_conflict].left_lines))

    def _take_right(self) -> None:
        if self._current_conflict < 0 or self._current_conflict >= len(self._conflicts):
            return
        self._resolve_current(list(self._conflicts[self._current_conflict].right_lines))

    def _take_base(self) -> None:
        if self._current_conflict < 0 or self._current_conflict >= len(self._conflicts):
            return
        self._resolve_current(list(self._conflicts[self._current_conflict].base_lines))

    def _take_both_lr(self) -> None:
        if self._current_conflict < 0 or self._current_conflict >= len(self._conflicts):
            return
        conflict = self._conflicts[self._current_conflict]
        combined = list(conflict.left_lines) + list(conflict.right_lines)
        self._resolve_current(combined)

    def _take_both_rl(self) -> None:
        if self._current_conflict < 0 or self._current_conflict >= len(self._conflicts):
            return
        conflict = self._conflicts[self._current_conflict]
        combined = list(conflict.right_lines) + list(conflict.left_lines)
        self._resolve_current(combined)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_merged(self) -> None:
        """Open a file dialog and save the merged output."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Merged File", "", "All Files (*)",
        )
        if not path:
            return

        try:
            Path(path).write_text(
                self._output_editor.toPlainText(), encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self.merge_saved.emit(path)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def clear_content(self) -> None:
        """Clear all panes."""
        self._left_editor.clear_content()
        self._base_editor.clear_content()
        self._right_editor.clear_content()
        self._output_editor.clear_content()
        self._conflicts.clear()
        self._current_conflict = -1
        self._update_conflict_label()
        self._left_label.setText("Left (Yours)")
        self._base_label.setText("Base (Ancestor)")
        self._right_label.setText("Right (Theirs)")
        self._output_label.setText("Output (Merged)")
