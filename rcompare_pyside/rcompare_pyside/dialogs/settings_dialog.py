"""Settings dialog for RCompare."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QTextEdit, QCheckBox, QPushButton,
    QFileDialog, QDialogButtonBox, QComboBox, QGroupBox,
    QFormLayout,
)

from ..models.settings import ComparisonSettings
from ..utils.config import AppConfig


class SettingsDialog(QDialog):
    """Settings dialog with tabs for General, Appearance, and CLI configuration."""

    def __init__(self, config: AppConfig, settings: ComparisonSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RCompare Settings")
        self.setMinimumSize(500, 400)
        self._config = config
        self._settings = settings

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # General tab
        general = QWidget()
        general_layout = QVBoxLayout(general)

        # Ignore patterns
        patterns_group = QGroupBox("Ignore Patterns")
        patterns_layout = QVBoxLayout(patterns_group)
        patterns_layout.addWidget(QLabel("One pattern per line (glob syntax):"))
        self._patterns_edit = QTextEdit()
        self._patterns_edit.setPlainText("\n".join(settings.ignore_patterns))
        self._patterns_edit.setMaximumHeight(120)
        patterns_layout.addWidget(self._patterns_edit)
        general_layout.addWidget(patterns_group)

        # Options
        options_group = QGroupBox("Comparison Options")
        options_layout = QFormLayout(options_group)
        self._symlinks_check = QCheckBox("Follow symbolic links")
        self._symlinks_check.setChecked(settings.follow_symlinks)
        options_layout.addRow(self._symlinks_check)
        self._hash_check = QCheckBox("Use hash verification for same-sized files")
        self._hash_check.setChecked(settings.use_hash_verification)
        options_layout.addRow(self._hash_check)

        cache_row = QHBoxLayout()
        self._cache_edit = QLineEdit(settings.cache_dir or "")
        self._cache_edit.setPlaceholderText("Default cache directory")
        cache_browse = QPushButton("Browse...")
        cache_browse.clicked.connect(self._browse_cache)
        cache_row.addWidget(self._cache_edit, 1)
        cache_row.addWidget(cache_browse)
        options_layout.addRow("Cache directory:", cache_row)
        general_layout.addWidget(options_group)
        general_layout.addStretch()
        tabs.addTab(general, "General")

        # Appearance tab
        appearance = QWidget()
        appearance_layout = QFormLayout(appearance)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Light", "Dark"])
        self._theme_combo.setCurrentText(config.theme.capitalize())
        appearance_layout.addRow("Theme:", self._theme_combo)
        appearance_layout.addRow(QLabel("Theme changes take effect after restart."))
        tabs.addTab(appearance, "Appearance")

        # CLI tab
        cli_tab = QWidget()
        cli_layout = QFormLayout(cli_tab)
        cli_row = QHBoxLayout()
        self._cli_edit = QLineEdit(config.cli_path or "")
        self._cli_edit.setPlaceholderText("Auto-detect")
        cli_browse = QPushButton("Browse...")
        cli_browse.clicked.connect(self._browse_cli)
        cli_row.addWidget(self._cli_edit, 1)
        cli_row.addWidget(cli_browse)
        cli_layout.addRow("rcompare_cli path:", cli_row)
        detect_btn = QPushButton("Auto-detect")
        detect_btn.clicked.connect(self._auto_detect_cli)
        cli_layout.addRow(detect_btn)
        tabs.addTab(cli_tab, "CLI")

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self) -> ComparisonSettings:
        patterns = [p.strip() for p in self._patterns_edit.toPlainText().splitlines() if p.strip()]
        return ComparisonSettings(
            ignore_patterns=patterns,
            follow_symlinks=self._symlinks_check.isChecked(),
            use_hash_verification=self._hash_check.isChecked(),
            cache_dir=self._cache_edit.text() or None,
        )

    def get_config_updates(self) -> dict:
        return {
            "theme": self._theme_combo.currentText().lower(),
            "cli_path": self._cli_edit.text() or None,
        }

    def _browse_cache(self):
        path = QFileDialog.getExistingDirectory(self, "Select Cache Directory")
        if path:
            self._cache_edit.setText(path)

    def _browse_cli(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select rcompare_cli Binary")
        if path:
            self._cli_edit.setText(path)

    def _auto_detect_cli(self):
        from ..utils.config import _find_cli
        found = _find_cli()
        if found:
            self._cli_edit.setText(found)
        else:
            self._cli_edit.setText("")
            self._cli_edit.setPlaceholderText("Not found - please set manually")
