"""Dialog for editing the active session's file filter (Beyond Compare style)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..utils.file_filter import PRESETS, parse_filter


class FileFiltersDialog(QDialog):
    def __init__(self, current: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("File Filters")
        self.setMinimumWidth(520)

        self._preset = QComboBox()
        for label, value in PRESETS:
            self._preset.addItem(label, value)
        self._preset.activated.connect(self._on_preset)

        self._edit = QLineEdit(current)
        self._edit.setPlaceholderText("*.py;*.rs;-build/;-*.tmp")
        self._edit.setClearButtonEnabled(True)
        self._edit.textChanged.connect(self._update_preview)

        self._preview = QLabel()
        self._preview.setWordWrap(True)

        hint = QLabel(
            "Separate entries with <b>;</b>. Plain globs <b>include</b> only matching files; "
            "a leading <b>-</b> <b>excludes</b>. A trailing <b>/</b> matches folders "
            "(<code>-build/</code>). Patterns containing <b>/</b> match the relative path."
        )
        hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Preset:", self._preset)
        form.addRow("Filter:", self._edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._preview)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self._update_preview()

    def _on_preset(self, index: int) -> None:
        self._edit.setText(str(self._preset.itemData(index) or ""))

    def _update_preview(self) -> None:
        flt = parse_filter(self._edit.text())
        if not flt.active:
            self._preview.setText("No filter: all files are compared.")
        else:
            self._preview.setText(
                f"{len(flt.includes)} include rule(s), {len(flt.excludes)} exclude rule(s)."
            )

    def filter_text(self) -> str:
        return self._edit.text().strip()
