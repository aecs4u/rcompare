"""Move/copy target dialog for file operations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MoveDialog(QDialog):
    """Dialog to choose a destination for moving or copying items."""

    def __init__(
        self,
        items: list[str],
        parent: QWidget | None = None,
        copy_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._items = items

        action = "Copy" if copy_mode else "Move"
        self.setWindowTitle(f"{action} Items")
        self.setMinimumSize(520, 400)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        count_label = QLabel(
            f"{action} {len(items)} item{'s' if len(items) != 1 else ''} to:"
        )
        count_label.setObjectName("moveTitle")
        layout.addWidget(count_label)

        dest_row = QHBoxLayout()
        dest_row.setContentsMargins(0, 0, 0, 0)
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Destination path")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_destination)
        dest_row.addWidget(self._dest_edit, 1)
        dest_row.addWidget(browse_btn)
        layout.addLayout(dest_row)

        item_list = QListWidget()
        item_list.addItems(items)
        item_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(item_list, 1)

        self._copy_check = QCheckBox("Copy instead of move")
        self._copy_check.setChecked(copy_mode)
        layout.addWidget(self._copy_check)

        self._preserve_check = QCheckBox("Preserve directory structure")
        self._preserve_check.setChecked(False)
        layout.addWidget(self._preserve_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(
            """
            QLabel#moveTitle {
                font-size: 16px;
                font-weight: 600;
                margin: 2px 0px 4px 0px;
            }
            """
        )

    def _browse_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Destination")
        if path:
            self._dest_edit.setText(path)

    @property
    def destination(self) -> str:
        return self._dest_edit.text()

    @property
    def is_copy(self) -> bool:
        return self._copy_check.isChecked()

    @property
    def preserve_structure(self) -> bool:
        return self._preserve_check.isChecked()
