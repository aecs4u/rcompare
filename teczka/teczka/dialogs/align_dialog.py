"""Manual alignment override dialog for folder comparisons."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class AlignDialog(QDialog):
    """Allow the user to manually align a file with a candidate from the other side."""

    def __init__(
        self,
        source_name: str,
        candidates: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manual Alignment")
        self.setMinimumSize(420, 360)

        self._candidates = candidates
        self._selected: str | None = None

        layout = QVBoxLayout(self)

        # Header label
        align_label = QLabel(f"Align: <b>{source_name}</b>")
        align_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(align_label)

        # Search filter
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Type to filter candidates...")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._filter_edit, 1)
        layout.addLayout(filter_row)

        # Candidate list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        for path in candidates:
            self._list.addItem(QListWidgetItem(path))
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list, 1)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_path(self) -> str | None:
        """Return the path the user selected for alignment, or ``None``."""
        return self._selected

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        """Show only candidates matching the filter text."""
        search = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            item.setHidden(bool(search) and search not in item.text().lower())

    def _on_double_click(self, item: QListWidgetItem) -> None:
        """Accept the dialog when an item is double-clicked."""
        self._selected = item.text()
        self.accept()

    def _on_accept(self) -> None:
        """Store the current selection and accept."""
        current = self._list.currentItem()
        if current is not None and not current.isHidden():
            self._selected = current.text()
        self.accept()
