"""Three-way merge view inspired by Beyond Compare and KDiff3."""

from __future__ import annotations

import difflib
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..widgets.diff_text_edit import DiffTextEdit
from ..workers.function_worker import FunctionWorker

# Highlight colors for merge regions
COLOR_LEFT = QColor("#bbdefb")       # blue tint - lines from left
COLOR_RIGHT = QColor("#c8e6c9")      # green tint - lines from right
COLOR_CONFLICT = QColor("#ffcdd2")   # red tint - unresolved conflict
COLOR_RESOLVED = QColor("#e0e0e0")   # light gray - resolved


COLOR_WHITE = QColor(Qt.GlobalColor.white)


@dataclass
class _MergeComputation:
    """Result of a background file-load + 3-way merge computation."""

    left_lines: list[str] = field(default_factory=list)
    base_lines: list[str] = field(default_factory=list)
    right_lines: list[str] = field(default_factory=list)
    conflicts: list[ConflictRegion] = field(default_factory=list)
    output_lines: list[str] = field(default_factory=list)
    output_colors: list[QColor] = field(default_factory=list)


def _compute_merge(left_path: str, base_path: str, right_path: str) -> _MergeComputation:
    """Read three files and perform the 3-way merge (runs off the GUI thread).

    Raises ``OSError`` if any file can't be read.
    """
    left_lines = Path(left_path).read_text(errors="replace").splitlines()
    base_lines = Path(base_path).read_text(errors="replace").splitlines()
    right_lines = Path(right_path).read_text(errors="replace").splitlines()

    conflicts, output_lines, output_colors = MergeView._merge_lines(
        left_lines, base_lines, right_lines
    )
    return _MergeComputation(
        left_lines=left_lines,
        base_lines=base_lines,
        right_lines=right_lines,
        conflicts=conflicts,
        output_lines=output_lines,
        output_colors=output_colors,
    )


class ConflictType(Enum):
    """Type of conflict region."""
    LEFT_ONLY = "left_only"
    RIGHT_ONLY = "right_only"
    BOTH_DIFFER = "conflict"


class ConflictRegion:
    """Tracks a single conflict in the merge output."""

    __slots__ = (
        "base_lines",
        "conflict_type",
        "end_line",
        "left_lines",
        "resolved",
        "right_lines",
        "start_line",
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
        self._pending_merge_paths: tuple[str, str, str] | None = None
        self._merge_worker: FunctionWorker | None = None

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
        """Read three files and perform a simple 3-way merge.

        File reads and the difflib-based merge computation run on a
        background thread (:class:`FunctionWorker`) so large files don't
        block the GUI.
        """
        self._left_path = left_path
        self._base_path = base_path
        self._right_path = right_path

        self._left_label.setText(f"Left (Yours) - {left_path}")
        self._base_label.setText(f"Base (Ancestor) - {base_path}")
        self._right_label.setText(f"Right (Theirs) - {right_path}")

        self._pending_merge_paths = (left_path, base_path, right_path)

        worker = FunctionWorker(_compute_merge, left_path, base_path, right_path, parent=self)
        worker.finished_with_result.connect(
            lambda result, paths=(left_path, base_path, right_path): self._on_merge_computed(paths, result)
        )
        worker.error.connect(
            lambda msg, paths=(left_path, base_path, right_path): self._on_merge_error(paths, msg)
        )
        worker.finished.connect(worker.deleteLater)
        self._merge_worker = worker
        worker.start()

    def _on_merge_computed(
        self, paths: tuple[str, str, str], result: _MergeComputation
    ) -> None:
        """Apply a background merge computation, if it's still the active request."""
        if self._pending_merge_paths != paths:
            return  # a newer load_merge() call superseded this one

        self._populate_source_panes(result.left_lines, result.base_lines, result.right_lines)
        self._conflicts = result.conflicts
        nums = [str(i + 1) for i in range(len(result.output_lines))]
        self._output_editor.set_content(result.output_lines, result.output_colors, nums)
        if self._conflicts:
            self._current_conflict = 0
            self._scroll_to_conflict(0)
        else:
            self._current_conflict = -1
        self._update_conflict_label()

    def _on_merge_error(self, paths: tuple[str, str, str], message: str) -> None:
        if self._pending_merge_paths != paths:
            return
        self._output_editor.setPlainText(f"Error reading files: {message}")

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

    @staticmethod
    def _merge_lines(
        left_lines: list[str],
        base_lines: list[str],
        right_lines: list[str],
    ) -> tuple[list[ConflictRegion], list[str], list[QColor]]:
        """Simple 3-way merge using difflib. Pure function (no Qt widget
        access) so it can run on a worker thread.

        Diff both sides against the base, group overlapping base spans, and
        compare each side's complete replacement for each span. Independent
        edits are applied in order; a region conflicts only when both sides
        changed it and their resulting lines differ.
        """
        left_ops = difflib.SequenceMatcher(None, base_lines, left_lines).get_opcodes()
        right_ops = difflib.SequenceMatcher(None, base_lines, right_lines).get_opcodes()

        output_lines: list[str] = []
        output_colors: list[QColor] = []
        conflicts: list[ConflictRegion] = []

        # Convert opcodes into a base-indexed structure
        left_changes = MergeView._opcodes_to_changes(left_ops, base_lines, left_lines)
        right_changes = MergeView._opcodes_to_changes(right_ops, base_lines, right_lines)

        edits = [
            (start, end, replacement, "left")
            for start, (end, replacement) in left_changes.items()
        ] + [
            (start, end, replacement, "right")
            for start, (end, replacement) in right_changes.items()
        ]
        edits.sort(key=lambda edit: (edit[0], edit[1], edit[3]))

        def overlaps_region(
            start: int, end: int, region_start: int, region_end: int
        ) -> bool:
            # Insertions at the same point (or at a replacement boundary)
            # participate in one decision; adjacent non-empty replacements
            # remain independent and can be combined automatically.
            if start == end:
                return region_start <= start <= region_end
            if region_start == region_end:
                return start <= region_start <= end
            return start < region_end and region_start < end

        def apply_region_edits(
            start: int,
            end: int,
            region_edits: list[tuple[int, int, list[str], str]],
        ) -> list[str]:
            patched: list[str] = []
            cursor = start
            for edit_start, edit_end, replacement, _side in sorted(
                region_edits, key=lambda edit: (edit[0], edit[1])
            ):
                if edit_start < cursor:
                    # Edits from one side are generated by a single diff and
                    # should not overlap. Keep this defensive guard explicit.
                    continue
                patched.extend(base_lines[cursor:edit_start])
                patched.extend(replacement)
                cursor = max(cursor, edit_end)
            patched.extend(base_lines[cursor:end])
            return patched

        # Fold edits that touch the same base region before comparing their
        # outcomes. This catches overlapping replacements with different
        # start indexes, which a start-index-only merge treated as separate.
        groups: list[list[tuple[int, int, list[str], str]]] = []
        group_start = 0
        group_end = 0
        for edit in edits:
            start, end, _replacement, _side = edit
            if not groups or not overlaps_region(start, end, group_start, group_end):
                groups.append([edit])
                group_start, group_end = start, end
            else:
                groups[-1].append(edit)
                group_start = min(group_start, start)
                group_end = max(group_end, end)

        next_base = 0
        for group in groups:
            region_start = min(edit[0] for edit in group)
            region_end = max(edit[1] for edit in group)
            if region_start > next_base:
                output_lines.extend(base_lines[next_base:region_start])
                output_colors.extend([COLOR_WHITE] * (region_start - next_base))

            base_slice = base_lines[region_start:region_end]
            left_edits = [edit for edit in group if edit[3] == "left"]
            right_edits = [edit for edit in group if edit[3] == "right"]
            left_result = apply_region_edits(region_start, region_end, left_edits)
            right_result = apply_region_edits(region_start, region_end, right_edits)

            if left_edits and right_edits and left_result != right_result:
                start_line = len(output_lines)
                output_lines.append("<<<< CONFLICT >>>>")
                output_lines.extend(left_result)
                output_lines.append("====")
                output_lines.extend(right_result)
                output_lines.append("<<<< END >>>>")
                output_colors.extend([COLOR_CONFLICT] * (len(output_lines) - start_line))
                conflicts.append(
                    ConflictRegion(
                        start_line,
                        len(output_lines),
                        ConflictType.BOTH_DIFFER,
                        left_result,
                        right_result,
                        base_slice,
                    )
                )
            else:
                merged = left_result if left_edits else right_result
                if left_edits and right_edits:
                    merged = left_result
                color = (
                    COLOR_RESOLVED
                    if left_edits and right_edits
                    else COLOR_LEFT
                    if left_edits
                    else COLOR_RIGHT
                )
                start_line = len(output_lines)
                output_lines.extend(merged)
                output_colors.extend([color] * len(merged))
                if merged:
                    conflict = ConflictRegion(
                        start_line,
                        len(output_lines),
                        ConflictType.BOTH_DIFFER
                        if left_edits and right_edits
                        else ConflictType.LEFT_ONLY
                        if left_edits
                        else ConflictType.RIGHT_ONLY,
                        left_result if left_edits else base_slice,
                        right_result if right_edits else base_slice,
                        base_slice,
                    )
                    conflict.resolved = True
                    conflicts.append(conflict)

            next_base = max(next_base, region_end)

        output_lines.extend(base_lines[next_base:])
        output_colors.extend([COLOR_WHITE] * (len(base_lines) - next_base))

        return conflicts, output_lines, output_colors

    @staticmethod
    def _opcodes_to_changes(
        opcodes: Sequence[tuple[str, int, int, int, int]],
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
