"""Dialog for choosing a per-extension external application."""

from __future__ import annotations

import shlex
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..utils.external_app import FILE_PLACEHOLDER, application_argv, handler_key


class OpenWithDialog(QDialog):
    """Select an application command and optionally remember it by extension."""

    def __init__(
        self,
        path: Path,
        initial_command: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self.setWindowTitle("Choose Application")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Choose an application for {path.name or path}. "
            f"Use {FILE_PLACEHOLDER} where the file path belongs. "
            "If omitted, the path is added at the end."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        command_row = QHBoxLayout()
        self._command_edit = QLineEdit(initial_command)
        self._command_edit.setObjectName("openWithCommand")
        self._command_edit.setPlaceholderText('e.g. "my editor" --wait {file}')
        command_row.addWidget(self._command_edit, 1)

        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_application)
        command_row.addWidget(browse_button)
        layout.addLayout(command_row)

        self._remember_check = QCheckBox(
            f"Remember for {handler_key(path)} files"
        )
        self._remember_check.setObjectName("openWithRemember")
        self._remember_check.setChecked(bool(handler_key(path)))
        layout.addWidget(self._remember_check)

        self._error_label = QLabel()
        self._error_label.setObjectName("openWithError")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #b00020;")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_command)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def command(self) -> str:
        return self._command_edit.text().strip()

    @property
    def remember(self) -> bool:
        return self._remember_check.isChecked()

    def _browse_application(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Application",
            str(self._path.parent),
            "Applications (*)",
        )
        if path:
            self._command_edit.setText(f"{shlex.quote(path)} {FILE_PLACEHOLDER}")

    def _accept_command(self) -> None:
        try:
            application_argv(self.command, self._path)
        except ValueError as exc:
            self._error_label.setText(str(exc))
            return
        self._error_label.clear()
        self.accept()
