"""Synchronize folders dialog for RCompare."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
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
    resume_requested = Signal(object)  # saved checkpoint metadata
    discard_requested = Signal(str)  # checkpoint id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synchronize Folders")
        self.setMinimumSize(760, 620)

        self._report: ScanReport | None = None
        self._left_root: str = ""
        self._right_root: str = ""

        layout = QVBoxLayout(self)

        # Operation mode
        mode_group = QGroupBox("Operation")
        mode_layout = QVBoxLayout(mode_group)
        self._mode_combo = QComboBox()
        for label, mode in (
            ("Update Right", "update_right"),
            ("Update Left", "update_left"),
            ("Update Both", "update_both"),
            ("Mirror to Right", "mirror_right"),
            ("Mirror to Left", "mirror_left"),
        ):
            self._mode_combo.addItem(label, mode)
        mode_layout.addWidget(self._mode_combo)
        layout.addWidget(mode_group)

        # Options group
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        self._dry_run_check = QCheckBox("Dry run")
        self._dry_run_check.setChecked(True)
        self._trash_check = QCheckBox("Move to trash instead of deleting")
        self._trash_check.setChecked(True)
        self._trash_check.setEnabled(False)
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

        # Saved sync recovery
        self._recovery_group = QGroupBox("Saved Sync Runs")
        recovery_layout = QVBoxLayout(self._recovery_group)
        self._recovery_status = QLabel(
            "Loading saved sync runs..."
        )
        self._recovery_status.setWordWrap(True)
        self._recovery_list = QListWidget()
        self._recovery_list.setMaximumHeight(120)
        recovery_layout.addWidget(self._recovery_status)
        recovery_layout.addWidget(self._recovery_list)
        recovery_buttons = QHBoxLayout()
        recovery_buttons.addStretch()
        self._resume_button = QPushButton("Resume Selected")
        self._discard_button = QPushButton("Discard Selected")
        self._resume_button.setEnabled(False)
        self._discard_button.setEnabled(False)
        recovery_buttons.addWidget(self._resume_button)
        recovery_buttons.addWidget(self._discard_button)
        recovery_layout.addLayout(recovery_buttons)
        layout.addWidget(self._recovery_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self._execute_btn = QPushButton("Execute")
        self._execute_btn.clicked.connect(self._on_execute)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._execute_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        # Recompute preview whenever sync options change
        self._mode_combo.currentIndexChanged.connect(self._update_preview)
        self._dry_run_check.toggled.connect(self._update_preview)
        self._trash_check.toggled.connect(self._update_preview)
        self._recovery_list.currentItemChanged.connect(self._update_recovery_buttons)
        self._resume_button.clicked.connect(self._resume_selected)
        self._discard_button.clicked.connect(self._discard_selected)

    def set_preview_source(self, report: ScanReport, left_root: str, right_root: str) -> None:
        """Provide compare data used to compute the sync preview."""
        self._report = report
        self._left_root = left_root
        self._right_root = right_root
        self._update_preview()

    def set_sync_enabled(self, enabled: bool, message: str = "") -> None:
        """Enable new sync actions only when the current report is reproducible."""
        self._execute_btn.setEnabled(enabled)
        self._mode_combo.setEnabled(enabled)
        self._dry_run_check.setEnabled(enabled)
        self._trash_check.setEnabled(
            enabled and self._get_direction() in {"mirror_left", "mirror_right"}
        )
        if not enabled:
            self._preview_edit.setPlainText(message)

    def set_recovery_checkpoints(
        self, checkpoints: list[dict], left_root: str, right_root: str
    ) -> None:
        """Show saved runs that belong to the currently selected root pair."""
        self._recovery_list.clear()
        matching = [
            checkpoint
            for checkpoint in checkpoints
            if checkpoint.get("left") == left_root
            and checkpoint.get("right") == right_root
        ]
        for checkpoint in matching:
            status = str(checkpoint.get("status", "unknown"))
            completed = int(checkpoint.get("completed_actions", 0))
            remaining = int(checkpoint.get("remaining_actions", 0))
            item = QListWidgetItem(
                f"{status.title()} — {completed} completed, {remaining} remaining"
            )
            item.setData(Qt.ItemDataRole.UserRole, checkpoint)
            self._recovery_list.addItem(item)

        if matching:
            self._recovery_status.setText(
                "Resume rescans both folders and skips work already reflected there. "
                "Discard removes the saved checkpoint metadata; partial destination "
                "files are left in place."
            )
            self._recovery_list.setCurrentRow(0)
        else:
            self._recovery_status.setText("No saved sync runs for this folder pair.")
        self._update_recovery_buttons()

    def set_recovery_error(self, message: str) -> None:
        """Show a checkpoint discovery error without blocking normal sync."""
        self._recovery_list.clear()
        self._recovery_status.setText(f"Could not load saved sync runs: {message}")
        self._update_recovery_buttons()

    def _update_recovery_buttons(self, *_args) -> None:
        item = self._recovery_list.currentItem()
        checkpoint = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._discard_button.setEnabled(isinstance(checkpoint, dict))
        self._resume_button.setEnabled(
            isinstance(checkpoint, dict) and checkpoint.get("status") != "completed"
        )

    def _resume_selected(self) -> None:
        item = self._recovery_list.currentItem()
        checkpoint = item.data(Qt.ItemDataRole.UserRole) if item else None
        if isinstance(checkpoint, dict) and checkpoint.get("status") != "completed":
            direction = str(checkpoint.get("direction", "left_to_right")).replace(
                "_", " "
            )
            delete_mode = str(checkpoint.get("delete_mode", "trash"))
            answer = QMessageBox.question(
                self,
                "Resume Saved Sync",
                f"Resume {direction} with {delete_mode} deletion for these folders? "
                "The CLI will rescan both folders and may modify their contents.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.resume_requested.emit(checkpoint)
            self.accept()

    def _discard_selected(self) -> None:
        item = self._recovery_list.currentItem()
        checkpoint = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(checkpoint, dict):
            return
        checkpoint_id = checkpoint.get("id")
        if not isinstance(checkpoint_id, str):
            return
        answer = QMessageBox.question(
            self,
            "Discard Saved Sync",
            "Remove this saved sync checkpoint and its partial-copy metadata? "
            "Any partial destination files will remain on disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.discard_requested.emit(checkpoint_id)

    def _get_direction(self) -> str:
        return str(self._mode_combo.currentData())

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

            if direction in {"left_to_right", "update_right", "mirror_right"}:
                if status == DiffStatus.ORPHAN_LEFT:
                    actions.append(SyncPreviewAction("COPY L->R", p, "Create on right"))
                elif status == DiffStatus.ORPHAN_RIGHT and direction != "update_right":
                    actions.append(SyncPreviewAction("DELETE R", p, "Remove from right"))
                elif status == DiffStatus.DIFFERENT:
                    actions.append(SyncPreviewAction("UPDATE R", p, "Overwrite from left"))
                continue

            if direction in {"right_to_left", "update_left", "mirror_left"}:
                if status == DiffStatus.ORPHAN_RIGHT:
                    actions.append(SyncPreviewAction("COPY R->L", p, "Create on left"))
                elif status == DiffStatus.ORPHAN_LEFT and direction != "update_left":
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
        direction = self._get_direction()
        is_mirror = direction in {"mirror_left", "mirror_right"}
        self._trash_check.setEnabled(is_mirror)
        if self._report is None:
            self._preview_edit.setPlainText(
                "Run a comparison first, then open Synchronize to preview planned actions."
            )
            return

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
        lines.append(f"Mode : {self._mode_combo.currentText()}")
        lines.append(
            "Run  : Dry run (no filesystem changes)"
            if dry_run
            else (
                "Run  : Execute changes after confirmation"
                if is_mirror
                else "Run  : Execute planned copy and update actions"
            )
        )
        if is_mirror:
            lines.append(
                "Delete handling: Move to trash"
                if use_trash
                else "Delete handling: Permanent delete"
            )
        elif direction in {"update_left", "update_right"}:
            lines.append("Orphans on the other side will be preserved.")
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
        actions = self._plan_actions()
        delete_actions = [
            action for action in actions if action.code in {"DELETE L", "DELETE R"}
        ]
        direction = self._get_direction()
        if direction in {"mirror_left", "mirror_right"} and not self._dry_run_check.isChecked():
            target = "left" if direction == "mirror_left" else "right"
            preview = (
                f"The preview lists {len(delete_actions)} target-only item(s) for removal. "
                "The CLI rescans both folders before applying changes, so this count may change."
                if delete_actions
                else "The preview found no target-only items. The CLI rescans both folders before "
                "applying changes, so new target-only items may be removed."
            )
            handling = (
                "The orphaned items will be moved to the trash."
                if self._trash_check.isChecked()
                else "This permanently deletes the orphaned items and cannot be undone."
            )
            answer = QMessageBox.question(
                self,
                "Confirm Mirror",
                f"Mirror to {target} removes target-only items. {preview} {handling} Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.sync_requested.emit(
            self._get_direction(),
            self._dry_run_check.isChecked(),
            self._trash_check.isChecked(),
        )
        self.accept()
