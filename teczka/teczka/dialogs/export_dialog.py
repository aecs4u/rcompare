"""Export comparison results to CSV, JSON, or plain text."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class ExportDialog(QDialog):
    """Dialog to choose export format and destination path."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Results")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        # -- Format selection --
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout(format_group)

        self._format_group = QButtonGroup(self)
        self._radio_csv = QRadioButton("CSV (comma-separated values)")
        self._radio_json = QRadioButton("JSON (structured data)")
        self._radio_text = QRadioButton("Plain Text")
        self._radio_csv.setChecked(True)

        self._format_group.addButton(self._radio_csv)
        self._format_group.addButton(self._radio_json)
        self._format_group.addButton(self._radio_text)

        format_layout.addWidget(self._radio_csv)
        format_layout.addWidget(self._radio_json)
        format_layout.addWidget(self._radio_text)
        layout.addWidget(format_group)

        # -- File path --
        path_group = QGroupBox("Destination")
        path_layout = QHBoxLayout(path_group)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select output file...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)

        path_layout.addWidget(self._path_edit, 1)
        path_layout.addWidget(browse_btn)
        layout.addWidget(path_group)

        # -- Options --
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._identical_check = QCheckBox("Include identical files")
        self._identical_check.setChecked(False)
        self._sizes_check = QCheckBox("Include file sizes")
        self._sizes_check.setChecked(True)

        options_layout.addWidget(self._identical_check)
        options_layout.addWidget(self._sizes_check)
        layout.addWidget(options_group)

        # -- Buttons --
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- Properties --

    @property
    def file_path(self) -> str:
        return self._path_edit.text()

    @property
    def format(self) -> str:
        if self._radio_json.isChecked():
            return "json"
        if self._radio_text.isChecked():
            return "text"
        return "csv"

    @property
    def include_identical(self) -> bool:
        return self._identical_check.isChecked()

    @property
    def include_sizes(self) -> bool:
        return self._sizes_check.isChecked()

    # -- Helpers --

    def _browse(self) -> None:
        filters = {
            "csv": "CSV Files (*.csv)",
            "json": "JSON Files (*.json)",
            "text": "Text Files (*.txt)",
        }
        selected_filter = filters.get(self.format, "All Files (*)")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Results", "", f"{selected_filter};;All Files (*)"
        )
        if path:
            self._path_edit.setText(path)

    # -- Static export logic --

    @staticmethod
    def export_results(
        results: list[dict],
        file_path: str,
        fmt: str,
        include_identical: bool,
        include_sizes: bool,
    ) -> None:
        """Write comparison results to *file_path* in the requested format."""

        filtered = results
        if not include_identical:
            filtered = [r for r in filtered if r.get("status") != "identical"]

        if not include_sizes:
            filtered = [
                {k: v for k, v in r.items() if k not in ("left_size", "right_size")}
                for r in filtered
            ]

        dest = Path(file_path)

        if fmt == "json":
            dest.write_text(json.dumps(filtered, indent=2, default=str), encoding="utf-8")

        elif fmt == "csv":
            if not filtered:
                dest.write_text("", encoding="utf-8")
                return
            fieldnames = list(filtered[0].keys())
            with dest.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(filtered)

        else:  # plain text
            lines: list[str] = []
            for entry in filtered:
                parts = [f"{k}: {v}" for k, v in entry.items()]
                lines.append("  ".join(parts))
            dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
