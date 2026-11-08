"""Smart selection dialog for folder-view items."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SelectDialog(QDialog):
    """Dialog to select or deselect items by criteria."""

    quick_select = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Smart Selection")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        scope = QLabel(
            "Selection uses rows accepted by the current Folder Compare filters, "
            "including rows inside collapsed folders. Search and view filters "
            "remain in effect."
        )
        scope.setObjectName("selectionScope")
        scope.setWordWrap(True)
        layout.addWidget(scope)

        # -- Quick buttons --
        quick_group = QGroupBox("Quick Selection")
        quick_layout = QHBoxLayout(quick_group)

        all_btn = QPushButton("All")
        all_btn.setObjectName("selectVisibleAll")
        none_btn = QPushButton("None")
        none_btn.setObjectName("selectVisibleNone")
        invert_btn = QPushButton("Invert")
        invert_btn.setObjectName("invertVisibleSelection")

        all_btn.clicked.connect(lambda: self.quick_select.emit("all"))
        none_btn.clicked.connect(lambda: self.quick_select.emit("none"))
        invert_btn.clicked.connect(lambda: self.quick_select.emit("invert"))

        quick_layout.addWidget(all_btn)
        quick_layout.addWidget(none_btn)
        quick_layout.addWidget(invert_btn)
        layout.addWidget(quick_group)

        # -- Criteria: status --
        status_group = QGroupBox("Filter by Status")
        status_layout = QVBoxLayout(status_group)

        self._status_identical = QCheckBox("Identical")
        self._status_different = QCheckBox("Different")
        self._status_left_only = QCheckBox("Left Only")
        self._status_right_only = QCheckBox("Right Only")
        self._left_newer = QCheckBox("Left Newer")
        self._right_newer = QCheckBox("Right Newer")

        for cb in (
            self._status_identical,
            self._status_different,
            self._status_left_only,
            self._status_right_only,
            self._left_newer,
            self._right_newer,
        ):
            cb.setChecked(
                cb
                in (
                    self._status_identical,
                    self._status_different,
                    self._status_left_only,
                    self._status_right_only,
                )
            )
            status_layout.addWidget(cb)

        layout.addWidget(status_group)

        side_group = QGroupBox("Selection Side")
        side_layout = QFormLayout(side_group)
        self._side_combo = QComboBox()
        self._side_combo.addItem("Left Panel", "left")
        self._side_combo.addItem("Right Panel", "right")
        self._side_combo.addItem("Both Panels", "both")
        side_layout.addRow("Select in:", self._side_combo)
        layout.addWidget(side_group)

        # -- Criteria: glob pattern --
        pattern_group = QGroupBox("Filter by Pattern")
        pattern_layout = QFormLayout(pattern_group)

        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText("e.g. *.txt")
        pattern_layout.addRow("Glob pattern:", self._pattern_edit)
        layout.addWidget(pattern_group)

        # -- Criteria: size --
        size_group = QGroupBox("Filter by Size")
        size_layout = QFormLayout(size_group)

        self._min_size_spin = QSpinBox()
        self._min_size_spin.setRange(0, 999_999_999)
        self._min_size_spin.setSuffix(" KB")
        self._min_size_spin.setValue(0)

        self._max_size_spin = QSpinBox()
        self._max_size_spin.setRange(0, 999_999_999)
        self._max_size_spin.setSuffix(" KB")
        self._max_size_spin.setValue(0)
        self._max_size_spin.setSpecialValueText("No limit")

        size_layout.addRow("Min size:", self._min_size_spin)
        size_layout.addRow("Max size:", self._max_size_spin)
        layout.addWidget(size_group)

        # -- Mode radio --
        mode_group = QGroupBox("Action")
        mode_layout = QVBoxLayout(mode_group)

        self._mode_group = QButtonGroup(self)
        self._radio_select = QRadioButton("Select matching")
        self._radio_deselect = QRadioButton("Deselect matching")
        self._radio_select.setChecked(True)

        self._mode_group.addButton(self._radio_select)
        self._mode_group.addButton(self._radio_deselect)

        mode_layout.addWidget(self._radio_select)
        mode_layout.addWidget(self._radio_deselect)
        layout.addWidget(mode_group)

        # -- Buttons --
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.accept
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- Properties --

    @property
    def criteria(self) -> dict:
        statuses: list[str] = []
        if self._status_identical.isChecked():
            statuses.append("identical")
        if self._status_different.isChecked():
            statuses.append("different")
        if self._status_left_only.isChecked():
            statuses.append("left_only")
        if self._status_right_only.isChecked():
            statuses.append("right_only")

        return {
            "statuses": statuses,
            "newer_sides": [
                side
                for side, checkbox in (
                    ("left", self._left_newer),
                    ("right", self._right_newer),
                )
                if checkbox.isChecked()
            ],
            "pattern": self._pattern_edit.text(),
            "min_size": self._min_size_spin.value(),
            "max_size": self._max_size_spin.value(),
            "mode": "select" if self._radio_select.isChecked() else "deselect",
            "side": self._side_combo.currentData(),
        }
