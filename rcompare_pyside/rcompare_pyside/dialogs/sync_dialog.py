"""Synchronize folders dialog for RCompare."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QCheckBox, QTextEdit, QPushButton,
    QDialogButtonBox,
)


class SyncDialog(QDialog):
    """Dialog for configuring and executing folder synchronization."""

    sync_requested = Signal(str, bool, bool)  # direction, dry_run, use_trash

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synchronize Folders")
        self.setMinimumSize(450, 350)

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
        self._preview_edit.setPlainText(
            "Sync preview will be shown here. Feature coming soon."
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

    def _get_direction(self) -> str:
        if self._left_to_right.isChecked():
            return "left_to_right"
        elif self._right_to_left.isChecked():
            return "right_to_left"
        else:
            return "bidirectional"

    def _on_execute(self):
        self.sync_requested.emit(
            self._get_direction(),
            self._dry_run_check.isChecked(),
            self._trash_check.isChecked(),
        )
        self.accept()
