"""About dialog for RCompare."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox


class AboutDialog(QDialog):
    """Simple about dialog displaying application information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About RCompare")
        self.setFixedSize(360, 200)

        layout = QVBoxLayout(self)

        name_label = QLabel("RCompare")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(name_label)

        version_label = QLabel("Version 0.1.0")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        desc_label = QLabel("High-performance file and directory comparison utility")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        frontend_label = QLabel("PySide6 Frontend")
        frontend_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(frontend_label)

        copyright_label = QLabel("\u00a9 2025 RCompare Contributors")
        copyright_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright_label)

        layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
