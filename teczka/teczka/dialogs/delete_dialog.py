"""Delete confirmation dialog for file operations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)


class DeleteDialog(QDialog):
    """Confirmation dialog that lists items to delete with trash/dry-run options."""

    def __init__(self, items: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items = items
        self._confirmed = False

        self.setWindowTitle("Confirm Delete")
        self.setMinimumSize(480, 360)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        count_label = QLabel(f"Delete {len(items)} item{'s' if len(items) != 1 else ''}?")
        count_label.setObjectName("deleteTitle")
        layout.addWidget(count_label)

        item_list = QListWidget()
        item_list.addItems(items)
        item_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(item_list, 1)

        self._trash_check = QCheckBox("Move to trash")
        self._trash_check.setChecked(True)
        layout.addWidget(self._trash_check)

        self._dry_run_check = QCheckBox("Dry run (preview only)")
        self._dry_run_check.setChecked(False)
        layout.addWidget(self._dry_run_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accepted)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(
            """
            QLabel#deleteTitle {
                font-size: 16px;
                font-weight: 600;
                margin: 2px 0px 4px 0px;
            }
            """
        )

    def _on_accepted(self) -> None:
        self._confirmed = True
        self.accept()

    @property
    def use_trash(self) -> bool:
        return self._trash_check.isChecked()

    @property
    def dry_run(self) -> bool:
        return self._dry_run_check.isChecked()

    @property
    def confirmed(self) -> bool:
        return self._confirmed
