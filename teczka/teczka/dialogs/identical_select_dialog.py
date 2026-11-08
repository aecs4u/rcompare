"""Options for 'Select Identical on LHS': files only, or folders too."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget,
)

from ..utils.bulk_select import find_identical


class IdenticalSelectDialog(QDialog):
    def __init__(self, report, folders_blocked_reason: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Identical on LHS")
        self.setMinimumWidth(460)
        self._report = report

        self._folders = QCheckBox("Also select folders that contain only identical items")
        self._folders.setToolTip(
            "A folder is selected only when it exists on both sides and everything\\n"
            "inside it is identical. Deleting it then removes the whole folder."
        )
        if folders_blocked_reason:
            self._folders.setEnabled(False)
            self._folders.setToolTip(folders_blocked_reason)
        self._folders.toggled.connect(self._refresh)

        self._counts = QLabel()
        self._note = QLabel(folders_blocked_reason)
        self._note.setWordWrap(True)
        self._note.setVisible(bool(folders_blocked_reason))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Select")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select identical items on the left panel:"))
        layout.addWidget(self._folders)
        layout.addWidget(self._note)
        layout.addWidget(self._counts)
        layout.addWidget(buttons)
        self._refresh()

    def include_folders(self) -> bool:
        return self._folders.isEnabled() and self._folders.isChecked()

    def _refresh(self) -> None:
        sel = find_identical(self._report, self.include_folders())
        self._counts.setText(f"{len(sel.files):,} file(s) and {len(sel.folders):,} folder(s) will be selected.")
