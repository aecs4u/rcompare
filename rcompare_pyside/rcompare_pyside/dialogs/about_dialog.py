"""KDE-style Help/About dialog for RCompare."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AboutDialog(QDialog):
    """Rich Help/About dialog with KDE-like structured layout."""

    PROJECT_URL = "https://github.com/aecs4u/rcompare"
    ISSUES_URL = "https://github.com/aecs4u/rcompare/issues"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RCompare Help")
        self.setMinimumSize(760, 560)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(self._build_header())

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_overview_tab(), "Overview")
        self._tabs.addTab(self._build_shortcuts_tab(), "Shortcuts")
        self._tabs.addTab(self._build_system_tab(), "System Info")
        root.addWidget(self._tabs, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self._btn_project = QPushButton("Project Page")
        self._btn_issues = QPushButton("Report Issue")
        self._btn_copy_debug = QPushButton("Copy Debug Info")
        actions.addWidget(self._btn_project)
        actions.addWidget(self._btn_issues)
        actions.addWidget(self._btn_copy_debug)
        actions.addStretch(1)
        root.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._btn_project.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.PROJECT_URL))
        )
        self._btn_issues.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.ISSUES_URL))
        )
        self._btn_copy_debug.clicked.connect(self._copy_debug_info)

        self._debug_text = self._collect_debug_info()
        self._debug_box.setPlainText(self._debug_text)

        # KDE Compliance: Use system theme instead of hardcoded styles
        # Keep only essential layout properties, let Qt handle colors
        self.setStyleSheet(
            """
            QLabel#badge {
                border-radius: 20px;
                font-size: 12px;
                font-weight: 700;
                qproperty-alignment: AlignCenter;
            }
            QLabel#title {
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#subtitle {
                font-size: 12px;
            }
            QTabBar::tab {
                min-width: 120px;
                padding: 6px 12px;
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
        badge.setFixedSize(40, 40)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        app = QApplication.instance()
        version = app.applicationVersion() if app is not None else "0.1.0"

        text_col = QVBoxLayout()
        title = QLabel("RCompare", hero)
        title.setObjectName("title")
        subtitle = QLabel(
            f"Version {version} - PySide Frontend for high-performance file comparison",
            hero,
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        text_col.addStretch(1)

        layout.addLayout(text_col, 1)
        return hero

    def _build_overview_tab(self) -> QWidget:
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("<b>What This App Does</b>", w)
        layout.addWidget(title)

        body = QLabel(
            "RCompare provides side-by-side directory and file comparison.\n"
            "It is designed for fast, practical workflows similar to KDE desktop tools.",
            w,
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        features = QTextEdit(w)
        features.setReadOnly(True)
        features.setHtml(
            "<b>Highlights</b><br>"
            "<ul>"
            "<li>Folder, text, hex, and image comparison views</li>"
            "<li>Multi-selection and copy actions</li>"
            "<li>Status filters including Files Only mode</li>"
            "<li>Session profiles and persistent per-user configuration</li>"
            "<li>Asynchronous comparison worker with progress reporting</li>"
            "</ul>"
            "<b>Tips</b><br>"
            "Use <b>Compare</b> to run scans, <b>F5</b> to refresh, "
            "and right-click rows for context actions."
        )
        layout.addWidget(features, 1)
        return w

    def _build_shortcuts_tab(self) -> QWidget:
        w = QWidget(self)
        grid = QGridLayout(w)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        shortcuts = [
            ("Ctrl+N", "Create a new session tab"),
            ("Ctrl+Q", "Quit application"),
            ("F5", "Refresh comparison"),
            ("F7", "Copy selected left -> right"),
            ("F8", "Copy selected right -> left"),
            ("Double-click row", "Open/switch to best matching compare view"),
            ("Right-click row", "Open context commands"),
        ]

        grid.addWidget(QLabel("<b>Shortcut</b>", w), 0, 0)
        grid.addWidget(QLabel("<b>Action</b>", w), 0, 1)
        for i, (key, desc) in enumerate(shortcuts, start=1):
            k = QLabel(key, w)
            k.setStyleSheet("font-family: monospace;")
            grid.addWidget(k, i, 0)
            grid.addWidget(QLabel(desc, w), i, 1)

        notes = QLabel(
            "Tip: Filter settings and options are stored per user and restored on startup.",
            w,
        )
        notes.setWordWrap(True)
        grid.addWidget(notes, len(shortcuts) + 2, 0, 1, 2)

        return w

    def _build_system_tab(self) -> QWidget:
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        info = QLabel("<b>Diagnostics</b> - include this when reporting issues.", w)
        layout.addWidget(info)

        self._debug_box = QTextEdit(w)
        self._debug_box.setReadOnly(True)
        self._debug_box.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._debug_box.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self._debug_box, 1)

        return w

    def _collect_debug_info(self) -> str:
        app = QApplication.instance()
        app_name = app.applicationName() if app is not None else "RCompare"
        app_version = app.applicationVersion() if app is not None else "0.1.0"
        config_path = Path.home() / ".config" / "rcompare" / "pyside.json"
        lines = [
            f"Application: {app_name}",
            f"Version: {app_version}",
            f"Frontend: PySide6",
            f"Qt: {qVersion()}",
            f"PySide6: {pyside_version}",
            f"Python: {sys.version.split()[0]}",
            f"Platform: {platform.platform()}",
            f"Machine: {platform.machine()}",
            f"Config: {config_path}",
        ]
        return "\n".join(lines)

    def _copy_debug_info(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(self._debug_text)
