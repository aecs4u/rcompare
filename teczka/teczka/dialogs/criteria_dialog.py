"""Dialog for choosing how files are judged equal (Beyond Compare style)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QSpinBox, QVBoxLayout, QWidget,
)

from ..utils.criteria import MODES, CompareCriteria


class CriteriaDialog(QDialog):
    def __init__(self, current: CompareCriteria, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Comparison Criteria")
        self.setMinimumWidth(440)

        self._mode = QComboBox()
        for key, label in MODES:
            self._mode.addItem(label, key)
        self._mode.setCurrentIndex(max(0, self._mode.findData(current.mode)))

        self._tol = QSpinBox()
        self._tol.setRange(0, 86400)
        self._tol.setSuffix(" s")
        self._tol.setValue(current.tolerance_s)
        self._tol.setToolTip("Modified times closer than this are treated as equal")

        self._hours = QCheckBox("Ignore whole-hour differences (DST / time zone)")
        self._hours.setChecked(current.ignore_hour_offsets)

        self._note = QLabel()
        self._note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Files are equal when:", self._mode)
        form.addRow("Timestamp tolerance:", self._tol)
        form.addRow("", self._hours)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._note)
        layout.addWidget(buttons)
        self._mode.currentIndexChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        mode = self._mode.currentData()
        uses_time = mode in ("time", "size_time")
        self._tol.setEnabled(uses_time)
        self._hours.setEnabled(uses_time)
        self._note.setText(
            "Content mode hashes same-sized files (accurate, slower)."
            if mode == "content"
            else "File contents are not read, so large folders compare much faster."
        )

    def criteria(self) -> CompareCriteria:
        return CompareCriteria(
            mode=str(self._mode.currentData()),
            tolerance_s=self._tol.value(),
            ignore_hour_offsets=self._hours.isChecked(),
        )
