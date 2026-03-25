"""Rename dialog for a single file."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class RenameDialog(QDialog):
    """Dialog to rename a single file with basic validation."""

    def __init__(self, current_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rename")
        self.setMinimumWidth(400)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        prompt = QLabel("Enter new name:")
        layout.addWidget(prompt)

        self._name_edit = QLineEdit(current_name)
        self._name_edit.selectAll()
        self._name_edit.textChanged.connect(self._validate)
        layout.addWidget(self._name_edit)

        self._error_label = QLabel("")
        self._error_label.setObjectName("renameError")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self.setStyleSheet(
            """
            QLabel#renameError {
                color: palette(highlight);
            }
            """
        )

        self._validate()

    def _validate(self) -> None:
        text = self._name_edit.text().strip()
        ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if not text:
            self._error_label.setText("Name cannot be empty.")
            if ok_btn is not None:
                ok_btn.setEnabled(False)
            return
        if os.sep in text or (os.altsep and os.altsep in text):
            self._error_label.setText("Name cannot contain path separators.")
            if ok_btn is not None:
                ok_btn.setEnabled(False)
            return
        self._error_label.setText("")
        if ok_btn is not None:
            ok_btn.setEnabled(True)

    @property
    def new_name(self) -> str:
        return self._name_edit.text().strip()
