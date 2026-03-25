"""Startup splash dialog with project overview and license access."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def _load_license_text() -> str:
    """Load project LICENSE text from likely repository/package locations."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "LICENSE",
        here.parents[2] / "LICENSE",
        Path.cwd() / "LICENSE",
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return "License file not found."


class LicenseDialog(QDialog):
    """Modal window displaying full license text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RCompare License")
        self.setModal(True)
        self.setMinimumSize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("<b>Full License Text</b>", self)
        layout.addWidget(title)

        self._text = QTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._text.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._text.setPlainText(_load_license_text())
        layout.addWidget(self._text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SplashDialog(QDialog):
    """Startup splash dialog with brief description and license entrypoint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to RCompare")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(620, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_header())
        root.addWidget(self._build_description())
        root.addWidget(self._build_license_panel())
        root.addStretch(1)

        buttons = QDialogButtonBox(self)
        self._btn_start = buttons.addButton("Start RCompare", QDialogButtonBox.ButtonRole.AcceptRole)
        self._btn_exit = buttons.addButton("Exit", QDialogButtonBox.ButtonRole.RejectRole)
        self._btn_start.clicked.connect(self.accept)
        self._btn_exit.clicked.connect(self.reject)
        root.addWidget(buttons)

        # KDE Compliance: Use system theme instead of hardcoded colors
        self.setStyleSheet(
            """
            QLabel#badge {
                border-radius: 22px;
                font-size: 14px;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
            }
            QLabel#title {
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#subtitle {
                font-size: 12px;
            }
            """
        )

    def _build_header(self) -> QWidget:
        hero = QFrame(self)
        hero.setObjectName("hero")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        badge = QLabel("RC", hero)
        badge.setObjectName("badge")
        badge.setFixedSize(44, 44)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        title = QLabel("RCompare", hero)
        title.setObjectName("title")
        subtitle = QLabel(
            "High-performance file and folder comparison for practical, daily workflows.",
            hero,
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        text_col.addStretch(1)
        layout.addLayout(text_col, 1)
        return hero

    def _build_description(self) -> QWidget:
        box = QFrame(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(4, 2, 4, 2)
        body = QLabel(
            "Use RCompare to inspect differences in folders and files with dedicated views for\n"
            "text, binary/hex, and images. Sync and copy actions are available from toolbar,\n"
            "menu, and right-click context commands.",
            box,
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        return box

    def _build_license_panel(self) -> QWidget:
        box = QFrame(self)
        box.setObjectName("licenseBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("<b>License Notice</b>", box)
        text = QLabel(
            "RCompare is distributed under the MIT License. "
            "You can review the full license text before using the application.",
            box,
        )
        text.setWordWrap(True)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_open = QPushButton("View Full License", box)
        btn_open.clicked.connect(self._open_license_dialog)
        btn_row.addWidget(btn_open)

        layout.addWidget(title)
        layout.addWidget(text)
        layout.addLayout(btn_row)
        return box

    def _open_license_dialog(self) -> None:
        dialog = LicenseDialog(self)
        dialog.exec()

