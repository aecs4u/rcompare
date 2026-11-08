"""Editor for per-session regular-expression text comparison rules."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..utils.unimportant_text import RuleValidationError, validate_rules


class UnimportantTextRulesDialog(QDialog):
    """Edit ordered pattern/replacement rules for text comparisons."""

    _HEADERS = ("Pattern", "Replacement", "Description")

    def __init__(self, rules: list[dict[str, str]] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Unimportant Text Rules")
        self.setMinimumSize(760, 420)

        self._table = QTableWidget(0, len(self._HEADERS), self)
        self._table.setHorizontalHeaderLabels(self._HEADERS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setToolTip(
            "Rules are applied in order to each line before text files are compared."
        )
        for rule in validate_rules(rules or []):
            self._add_row(rule)

        hint = QLabel(
            "Rules run from top to bottom on each line. Use a regular expression "
            "and replacement text; a blank replacement removes the matched text."
        )
        hint.setWordWrap(True)

        add_button = QPushButton("Add Rule", self)
        remove_button = QPushButton("Remove Selected", self)
        add_button.clicked.connect(self._add_row)
        remove_button.clicked.connect(self._remove_selected)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self._table, 1)
        layout.addLayout(row_buttons)
        layout.addWidget(buttons)

    def _add_row(self, rule: dict[str, str] | None = None) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        values = rule or {"pattern": "", "replacement": "", "description": ""}
        for column, key in enumerate(("pattern", "replacement", "description")):
            self._table.setItem(row, column, QTableWidgetItem(values[key]))
        self._table.setCurrentCell(row, 0)

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._table.removeRow(row)

    def rules(self) -> list[dict[str, str]]:
        """Return the rules in their displayed order."""
        result = []
        for row in range(self._table.rowCount()):
            values = [
                self._table.item(row, column).text() if self._table.item(row, column) else ""
                for column in range(len(self._HEADERS))
            ]
            if any(value.strip() for value in values):
                result.append(
                    {
                        "pattern": values[0],
                        "replacement": values[1],
                        "description": values[2],
                    }
                )
        return validate_rules(result)

    def accept(self) -> None:
        try:
            self.rules()
        except RuleValidationError as exc:
            QMessageBox.warning(self, "Invalid Text Rule", str(exc))
            return
        super().accept()
