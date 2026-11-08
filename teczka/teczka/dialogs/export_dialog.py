"""Export the currently visible comparison rows to a report file."""

from __future__ import annotations

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

from ..utils.report_export import export_folder_report


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
        self._radio_html = QRadioButton("HTML (readable report)")
        self._radio_xml = QRadioButton("XML (structured data)")
        self._radio_csv.setChecked(True)

        self._format_group.addButton(self._radio_csv)
        self._format_group.addButton(self._radio_json)
        self._format_group.addButton(self._radio_text)
        self._format_group.addButton(self._radio_html)
        self._format_group.addButton(self._radio_xml)
        self._format_group.buttonToggled.connect(self._on_format_toggled)

        format_layout.addWidget(self._radio_csv)
        format_layout.addWidget(self._radio_json)
        format_layout.addWidget(self._radio_text)
        format_layout.addWidget(self._radio_html)
        format_layout.addWidget(self._radio_xml)
        layout.addWidget(format_group)

        # -- File path --
        path_group = QGroupBox("Destination")
        path_layout = QHBoxLayout(path_group)

        self._path_edit = QLineEdit()
        self._path_edit.setText("comparison.csv")
        self._path_edit.setPlaceholderText("Select output file...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)

        path_layout.addWidget(self._path_edit, 1)
        path_layout.addWidget(browse_btn)
        layout.addWidget(path_group)

        # -- Options --
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._sizes_check = QCheckBox("Include file sizes")
        self._sizes_check.setChecked(True)

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
        if self._radio_html.isChecked():
            return "html"
        if self._radio_xml.isChecked():
            return "xml"
        return "csv"

    @property
    def include_identical(self) -> bool:
        """Compatibility property; report rows always follow the active view filters."""
        return True

    @property
    def include_sizes(self) -> bool:
        return self._sizes_check.isChecked()

    # -- Helpers --

    def _browse(self) -> None:
        filters = {
            "csv": "CSV Files (*.csv)",
            "json": "JSON Files (*.json)",
            "text": "Text Files (*.txt)",
            "html": "HTML Files (*.html *.htm)",
            "xml": "XML Files (*.xml)",
        }
        selected_filter = filters.get(self.format, "All Files (*)")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Results", self._path_edit.text(), f"{selected_filter};;All Files (*)"
        )
        if path:
            self._path_edit.setText(path)

    def _on_format_toggled(self, button: QRadioButton, checked: bool) -> None:
        if not checked:
            return
        extensions = {
            "csv": ".csv",
            "json": ".json",
            "text": ".txt",
            "html": ".html",
            "xml": ".xml",
        }
        if self._path_edit.text().startswith("comparison."):
            self._path_edit.setText("comparison" + extensions[self.format])

    # -- Static export logic --

    @staticmethod
    def export_results(
        results: list[dict],
        file_path: str,
        fmt: str,
        include_identical: bool = True,
        include_sizes: bool = True,
        *,
        left_root: str = "",
        right_root: str = "",
    ) -> None:
        """Write comparison results to *file_path* in the requested format.

        ``include_identical`` remains accepted for callers of the original
        helper. New GUI exports pass rows already accepted by the folder view,
        so the active status filters are authoritative.
        """
        filtered = results
        if not include_identical:
            filtered = [
                r for r in filtered
                if str(r.get("status", "")).lower() not in {"same", "identical"}
            ]
        if not include_sizes:
            filtered = [
                {k: v for k, v in r.items() if k not in ("left_size", "right_size")}
                for r in filtered
            ]
        export_folder_report(
            filtered,
            file_path,
            fmt,
            left_root=left_root,
            right_root=right_root,
            include_sizes=include_sizes,
        )
