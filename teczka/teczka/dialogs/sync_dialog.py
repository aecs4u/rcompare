"""Synchronize folders dialog for RCompare."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QCheckBox, QTextEdit, QPushButton,
)

from ..utils.cli_bridge import DiffEntry, DiffStatus, ScanReport


@dataclass
class SyncPreviewAction:
    """One planned sync action line."""

    code: str
    path: str
    detail: str


class SyncDialog(QDialog):
    """Dialog for configuring and executing folder synchronization."""

    sync_requested = Signal(str, bool, bool)  # direction, dry_run, use_trash

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synchronize Folders")
        self.setMinimumSize(720, 500)

        self._report: Optional[ScanReport] = None
        self._left_root: str = ""
        self._right_root: str = ""

        layout = QVBoxLayout(self)

        # Direction group
        direction_group = QGroupBox("Direction")
        direction_layout = QVBoxLayout(direction_group)
        self._left_to_right = QRadioButton("Left to Right")
        self._left_to_right.setChecked(True)
        self._right_to_left = QRadioButton("Right to Left")
        self._bidirectional = QRadioButton("Bidirectional")
        direction_layout.addWidget(self._left_to_right)
        direction_layout.addWidget(self._right_to_left)
        direction_layout.addWidget(self._bidirectional)
        layout.addWidget(direction_group)

        # Options group
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        self._dry_run_check = QCheckBox("Dry run")
        self._dry_run_check.setChecked(True)
        self._trash_check = QCheckBox("Move to trash instead of deleting")
        self._trash_check.setChecked(True)
        options_layout.addWidget(self._dry_run_check)
        options_layout.addWidget(self._trash_check)
        layout.addWidget(options_group)

        # Preview area
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        self._preview_edit = QTextEdit()
        self._preview_edit.setReadOnly(True)
        self._preview_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._preview_edit.setPlainText(
            "Run a comparison first, then open Synchronize to preview planned actions."
        )
        preview_layout.addWidget(self._preview_edit)
        layout.addWidget(preview_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        execute_btn = QPushButton("Execute")
        execute_btn.clicked.connect(self._on_execute)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(execute_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        # Recompute preview whenever sync options change
        self._left_to_right.toggled.connect(self._update_preview)
        self._right_to_left.toggled.connect(self._update_preview)
        self._bidirectional.toggled.connect(self._update_preview)
        self._dry_run_check.toggled.connect(self._update_preview)
        self._trash_check.toggled.connect(self._update_preview)

    def set_preview_source(self, report: ScanReport, left_root: str, right_root: str) -> None:
        """Provide compare data used to compute the sync preview."""
        self._report = report
        self._left_root = left_root
        self._right_root = right_root
        self._update_preview()

    def _get_direction(self) -> str:
        if self._left_to_right.isChecked():
            return "left_to_right"
        elif self._right_to_left.isChecked():
            return "right_to_left"
        else:
            return "bidirectional"

    def _fmt_path(self, entry: DiffEntry) -> str:
        is_dir = bool(
            (entry.left is not None and entry.left.is_dir)
            or (entry.right is not None and entry.right.is_dir)
        )
        p = PurePosixPath(entry.path).as_posix()
        return f"{p}/" if is_dir else p

    def _plan_actions(self) -> list[SyncPreviewAction]:
        report = self._report
        if report is None:
            return []

        direction = self._get_direction()
        actions: list[SyncPreviewAction] = []
        for entry in sorted(report.entries, key=lambda e: e.path):
            status = entry.status
            p = self._fmt_path(entry)

            if status == DiffStatus.SAME:
                continue

            if status == DiffStatus.UNCHECKED:
                actions.append(
                    SyncPreviewAction("SKIP", p, "Unchecked item; manual review required"),
                )
                continue

            if direction == "left_to_right":
                if status == DiffStatus.ORPHAN_LEFT:
                    actions.append(SyncPreviewAction("COPY L->R", p, "Create on right"))
                elif status == DiffStatus.ORPHAN_RIGHT:
                    actions.append(SyncPreviewAction("DELETE R", p, "Remove from right"))
                elif status == DiffStatus.DIFFERENT:
                    actions.append(SyncPreviewAction("UPDATE R", p, "Overwrite from left"))
                continue

            if direction == "right_to_left":
                if status == DiffStatus.ORPHAN_RIGHT:
                    actions.append(SyncPreviewAction("COPY R->L", p, "Create on left"))
                elif status == DiffStatus.ORPHAN_LEFT:
                    actions.append(SyncPreviewAction("DELETE L", p, "Remove from left"))
                elif status == DiffStatus.DIFFERENT:
                    actions.append(SyncPreviewAction("UPDATE L", p, "Overwrite from right"))
                continue

            # Bidirectional mode
            if status == DiffStatus.ORPHAN_LEFT:
                actions.append(SyncPreviewAction("COPY L->R", p, "Missing on right"))
            elif status == DiffStatus.ORPHAN_RIGHT:
                actions.append(SyncPreviewAction("COPY R->L", p, "Missing on left"))
            elif status == DiffStatus.DIFFERENT:
                left_m = entry.left.modified_unix if entry.left else None
                right_m = entry.right.modified_unix if entry.right else None
                if left_m is not None and right_m is not None:
                    if left_m > right_m:
                        actions.append(
                            SyncPreviewAction(
                                "COPY L->R", p, "Left newer in bidirectional mode",
                            ),
                        )
                    elif right_m > left_m:
                        actions.append(
                            SyncPreviewAction(
                                "COPY R->L", p, "Right newer in bidirectional mode",
                            ),
                        )
                    else:
                        actions.append(
                            SyncPreviewAction(
                                "CONFLICT",
                                p,
                                "Same timestamp but different content; manual review",
                            ),
                        )
                else:
                    actions.append(
                        SyncPreviewAction(
                            "CONFLICT",
                            p,
                            "Cannot determine newer side; manual review",
                        ),
                    )

        return actions

    def _update_preview(self) -> None:
        if self._report is None:
            self._preview_edit.setPlainText(
                "Run a comparison first, then open Synchronize to preview planned actions."
            )
            return

        direction = self._get_direction()
        dry_run = self._dry_run_check.isChecked()
        use_trash = self._trash_check.isChecked()
        actions = self._plan_actions()

        counts: dict[str, int] = {}
        for action in actions:
            counts[action.code] = counts.get(action.code, 0) + 1

        lines: list[str] = []
        lines.append("Synchronization Preview")
        lines.append("=" * 78)
        lines.append(f"Left : {self._left_root}")
        lines.append(f"Right: {self._right_root}")
        lines.append(f"Mode : {direction}")
        lines.append(
            "Run  : Dry run (no filesystem changes)"
            if dry_run
            else "Run  : Execute changes on confirmation"
        )
        lines.append(
            "Delete handling: Move to trash" if use_trash else "Delete handling: Permanent delete"
        )
        lines.append("")

        if not actions:
            lines.append("No synchronization actions are required.")
            self._preview_edit.setPlainText("\n".join(lines))
            return

        lines.append("Summary:")
        for code in sorted(counts):
            lines.append(f"  {code:10} : {counts[code]}")
        lines.append("")
        lines.append("Planned Operations:")

        max_lines = 300
        for i, action in enumerate(actions):
            if i >= max_lines:
                lines.append(f"... and {len(actions) - max_lines} more actions")
                break
            lines.append(f"[{action.code:10}] {action.path}  -- {action.detail}")

        self._preview_edit.setPlainText("\n".join(lines))

    def _on_execute(self):
        self.sync_requested.emit(
            self._get_direction(),
            self._dry_run_check.isChecked(),
            self._trash_check.isChecked(),
        )
        self.accept()
