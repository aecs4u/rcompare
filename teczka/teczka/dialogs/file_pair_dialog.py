"""Dialog for selecting an explicit pair of files to compare."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..utils.source_paths import is_remote_source, split_source_file


class FilePairDialog(QDialog):
    """Collect two existing files without requiring parent-folder scans."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare Two Files")
        self.setMinimumWidth(620)

        self._left_path = QLineEdit(self)
        self._left_path.setObjectName("leftFilePath")
        self._left_path.setPlaceholderText("Choose a local file or enter a remote URL")
        self._right_path = QLineEdit(self)
        self._right_path.setObjectName("rightFilePath")
        self._right_path.setPlaceholderText(
            "Choose a local file or enter a remote URL"
        )
        self._message = QLabel(
            "Select local files or enter remote URLs. "
            "Do not include credentials in URLs.",
            self,
        )
        self._message.setWordWrap(True)

        layout = QVBoxLayout(self)
        rows = QGridLayout()
        rows.addWidget(QLabel("Left file or URL", self), 0, 0)
        rows.addWidget(self._left_path, 0, 1)
        left_browse = QPushButton("Browse…", self)
        left_browse.clicked.connect(
            lambda: self._browse(self._left_path, "Select Left File")
        )
        rows.addWidget(left_browse, 0, 2)
        rows.addWidget(QLabel("Right file or URL", self), 1, 0)
        rows.addWidget(self._right_path, 1, 1)
        right_browse = QPushButton("Browse…", self)
        right_browse.clicked.connect(
            lambda: self._browse(self._right_path, "Select Right File")
        )
        rows.addWidget(right_browse, 1, 2)
        rows.setColumnStretch(1, 1)
        layout.addLayout(rows)
        layout.addWidget(self._message)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText("Compare")
        self._ok_button.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._left_path.textChanged.connect(self._update_validation)
        self._right_path.textChanged.connect(self._update_validation)

    def selected_files(self) -> tuple[Path | str, Path | str] | None:
        """Return local paths and remote URLs after validation."""
        left = self._validated_source(self._left_path.text())
        right = self._validated_source(self._right_path.text())
        if left is None or right is None:
            return None
        return left, right

    def accept(self) -> None:
        """Accept only local files or supported remote file URLs."""
        self._update_validation()
        if not self._ok_button.isEnabled():
            return
        super().accept()

    def _browse(self, field: QLineEdit, title: str) -> None:
        current_value = field.text().strip()
        start_directory = "" if is_remote_source(current_value) else current_value
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            start_directory,
            "All files (*)",
        )
        if path:
            field.setText(path)

    def _update_validation(self, *_args) -> None:
        valid = self._validated_source(self._left_path.text()) is not None and (
            self._validated_source(self._right_path.text()) is not None
        )
        self._ok_button.setEnabled(valid)
        if valid:
            message = (
                "Ready to compare the selected files. "
                "Remote access uses the configured CLI credentials."
            )
        else:
            message = (
                "Select existing local files or enter valid s3, sftp, dav, or "
                "davs file URLs."
            )
        self._message.setText(message)

    @staticmethod
    def _validated_source(value: str) -> Path | str | None:
        value = value.strip()
        if not value:
            return None
        try:
            split_source_file(value)
        except ValueError:
            return None
        return value if is_remote_source(value) else Path(value).expanduser()
