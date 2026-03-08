"""Settings dialog for RCompare."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QFontDatabase, QIcon

from ..models.settings import ComparisonSettings
from ..utils.config import AppConfig


class SettingsDialog(QDialog):
    """KDE-style settings dialog with category tabs and grouped sections."""

    def __init__(self, config: AppConfig, settings: ComparisonSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure RCompare")
        self.setMinimumSize(760, 520)
        self._config = config
        self._settings = settings

        layout = QVBoxLayout(self)

        title = QLabel("System Settings")
        title.setObjectName("settingsTitle")
        subtitle = QLabel("Configure comparison behavior, UI appearance, and CLI integration.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("settingsSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._tabs.setUsesScrollButtons(False)
        layout.addWidget(self._tabs, 1)

        self._build_general_tab()
        self._build_diff_options_tab()
        self._build_appearance_tab()
        self._build_cli_tab()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        defaults_btn = buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        if defaults_btn is not None:
            defaults_btn.setText("Defaults")
            defaults_btn.clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Local dialog polish (matches KDE-like structured settings windows).
        self.setStyleSheet(
            """
            QLabel#settingsTitle {
                font-size: 16px;
                font-weight: 600;
                margin: 2px 0px 0px 0px;
            }
            QLabel#settingsSubtitle {
                color: palette(mid);
                margin: 0px 0px 6px 0px;
            }
            QGroupBox {
                margin-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                font-weight: 600;
            }
            """
        )

    def _build_general_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        behavior_group = QGroupBox("Comparison Behavior")
        behavior_layout = QVBoxLayout(behavior_group)
        self._symlinks_check = QCheckBox("Follow symbolic links")
        self._symlinks_check.setChecked(self._settings.follow_symlinks)
        self._hash_check = QCheckBox("Use hash verification for same-sized files")
        self._hash_check.setChecked(self._settings.use_hash_verification)
        behavior_hint = QLabel(
            "Hash verification improves accuracy but can increase scan time."
        )
        behavior_hint.setWordWrap(True)
        behavior_layout.addWidget(self._symlinks_check)
        behavior_layout.addWidget(self._hash_check)
        behavior_layout.addWidget(behavior_hint)
        layout.addWidget(behavior_group)

        cache_group = QGroupBox("Cache")
        cache_layout = QFormLayout(cache_group)
        cache_row_widget = QWidget()
        cache_row = QHBoxLayout(cache_row_widget)
        cache_row.setContentsMargins(0, 0, 0, 0)
        self._cache_edit = QLineEdit(self._settings.cache_dir or "")
        self._cache_edit.setPlaceholderText("Default cache directory")
        cache_browse = QPushButton("Browse...")
        cache_browse.clicked.connect(self._browse_cache)
        cache_clear = QPushButton("Clear")
        cache_clear.clicked.connect(self._cache_edit.clear)
        cache_row.addWidget(self._cache_edit, 1)
        cache_row.addWidget(cache_browse)
        cache_row.addWidget(cache_clear)
        cache_layout.addRow("Cache directory:", cache_row_widget)
        layout.addWidget(cache_group)

        patterns_group = QGroupBox("Ignore Patterns")
        patterns_layout = QVBoxLayout(patterns_group)
        patterns_hint = QLabel("One glob pattern per line. Example: `*.tmp` or `build/**`")
        patterns_hint.setWordWrap(True)
        self._patterns_edit = QTextEdit()
        self._patterns_edit.setPlainText("\n".join(self._settings.ignore_patterns))
        self._patterns_edit.setMinimumHeight(160)
        self._patterns_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        patterns_layout.addWidget(patterns_hint)
        patterns_layout.addWidget(self._patterns_edit)
        layout.addWidget(patterns_group, 1)

        self._tabs.addTab(tab, self._icon("configure"), "General")

    def _build_diff_options_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Whitespace handling
        ws_group = QGroupBox("Whitespace Handling")
        ws_layout = QFormLayout(ws_group)
        self._ws_combo = QComboBox()
        self._ws_combo.addItems(["None", "All", "Leading", "Trailing", "Changes"])
        ws_layout.addRow("Ignore whitespace:", self._ws_combo)
        layout.addWidget(ws_group)

        # Text comparison options
        text_group = QGroupBox("Text Comparison")
        text_layout = QVBoxLayout(text_group)
        self._case_check = QCheckBox("Ignore case differences")
        text_layout.addWidget(self._case_check)
        self._text_diff_check = QCheckBox("Enable line-by-line text diff")
        self._text_diff_check.setChecked(True)
        text_layout.addWidget(self._text_diff_check)
        layout.addWidget(text_group)

        # Specialized comparisons
        spec_group = QGroupBox("Specialized Comparisons")
        spec_layout = QVBoxLayout(spec_group)
        self._image_diff_check = QCheckBox("Enable pixel-level image comparison")
        spec_layout.addWidget(self._image_diff_check)
        self._csv_diff_check = QCheckBox("Enable CSV row-by-row comparison")
        spec_layout.addWidget(self._csv_diff_check)
        self._json_diff_check = QCheckBox("Enable JSON/YAML structural comparison")
        spec_layout.addWidget(self._json_diff_check)
        self._excel_diff_check = QCheckBox("Enable Excel sheet/cell comparison")
        spec_layout.addWidget(self._excel_diff_check)
        layout.addWidget(spec_group)

        # Regex rules
        regex_group = QGroupBox("Regex Normalization Rules")
        regex_layout = QVBoxLayout(regex_group)
        regex_hint = QLabel("Format: pattern:replacement:description (one per line)")
        regex_hint.setWordWrap(True)
        self._regex_edit = QTextEdit()
        self._regex_edit.setMinimumHeight(80)
        self._regex_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._regex_edit.setPlaceholderText(
            r"\d{4}-\d{2}-\d{2}:[DATE]:Normalize dates"
        )
        regex_layout.addWidget(regex_hint)
        regex_layout.addWidget(self._regex_edit)
        layout.addWidget(regex_group, 1)

        self._tabs.addTab(tab, self._icon("text-x-generic"), "Diff Options")

    def _build_appearance_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        appearance_group = QGroupBox("Theme")
        appearance_layout = QFormLayout(appearance_group)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Light", "Dark"])
        current_theme = self._config.theme.strip().capitalize()
        if current_theme not in {"Light", "Dark"}:
            current_theme = "Light"
        self._theme_combo.setCurrentText(current_theme)
        self._theme_hint = QLabel("")
        self._theme_hint.setWordWrap(True)
        self._theme_combo.currentTextChanged.connect(self._update_theme_hint)
        self._update_theme_hint(self._theme_combo.currentText())
        appearance_layout.addRow("Color theme:", self._theme_combo)
        appearance_layout.addRow(self._theme_hint)
        layout.addWidget(appearance_group)

        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        notes = QLabel(
            "Theme changes are applied when the application restarts. "
            "All theme choices are stored per user."
        )
        notes.setWordWrap(True)
        notes_layout.addWidget(notes)
        layout.addWidget(notes_group)
        layout.addStretch()

        self._tabs.addTab(tab, self._icon("preferences-desktop-theme"), "Appearance")

    def _build_cli_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        cli_group = QGroupBox("rcompare_cli Binary")
        cli_layout = QFormLayout(cli_group)

        cli_row_widget = QWidget()
        cli_row = QHBoxLayout(cli_row_widget)
        cli_row.setContentsMargins(0, 0, 0, 0)
        self._cli_edit = QLineEdit(self._config.cli_path or "")
        self._cli_edit.setPlaceholderText("Auto-detect")
        self._cli_edit.textChanged.connect(self._update_cli_status)
        cli_browse = QPushButton("Browse...")
        cli_browse.clicked.connect(self._browse_cli)
        cli_row.addWidget(self._cli_edit, 1)
        cli_row.addWidget(cli_browse)
        cli_layout.addRow("Path:", cli_row_widget)

        actions_row = QWidget()
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        detect_btn = QPushButton("Auto-detect")
        detect_btn.clicked.connect(self._auto_detect_cli)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._cli_edit.clear)
        actions_layout.addWidget(detect_btn)
        actions_layout.addWidget(clear_btn)
        actions_layout.addStretch()
        cli_layout.addRow(actions_row)

        self._cli_status_label = QLabel("")
        self._cli_status_label.setWordWrap(True)
        cli_layout.addRow("Status:", self._cli_status_label)
        layout.addWidget(cli_group)

        help_group = QGroupBox("Detection")
        help_layout = QVBoxLayout(help_group)
        help_text = QLabel(
            "Auto-detect checks PATH and common Cargo target directories "
            "(including `target/release` and `target/debug`)."
        )
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)
        layout.addWidget(help_group)
        layout.addStretch()

        self._tabs.addTab(tab, self._icon("applications-development"), "CLI")
        self._update_cli_status()

    def _icon(self, name: str) -> QIcon:
        return QIcon.fromTheme(name)

    def _update_theme_hint(self, theme_name: str) -> None:
        if theme_name.lower() == "dark":
            self._theme_hint.setText("Dark theme selected. Change takes effect after restart.")
        else:
            self._theme_hint.setText("Light theme selected. Change takes effect after restart.")

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

    def _restore_defaults(self) -> None:
        reply = QMessageBox.question(
            self,
            "Restore Defaults",
            "Reset all options in this window to default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._patterns_edit.clear()
        self._symlinks_check.setChecked(False)
        self._hash_check.setChecked(True)
        self._cache_edit.clear()
        self._theme_combo.setCurrentText("Light")
        self._auto_detect_cli()

    def _browse_cache(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Cache Directory")
        if path:
            self._cache_edit.setText(path)

    def _browse_cli(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select rcompare_cli Binary")
        if path:
            self._cli_edit.setText(path)

    def _auto_detect_cli(self) -> None:
        from ..utils.config import _find_cli
        found = _find_cli()
        if found:
            self._cli_edit.setText(found)
        else:
            self._cli_edit.setText("")
            self._cli_edit.setPlaceholderText("Not found - please set manually")

    def _update_cli_status(self) -> None:
        raw = self._cli_edit.text().strip()
        if not raw:
            self._cli_status_label.setText(
                "Path empty. The app will auto-detect on next validation."
            )
            return
        candidate = Path(raw)
        if not candidate.exists():
            self._cli_status_label.setText("Selected path does not exist.")
            return
        if not candidate.is_file():
            self._cli_status_label.setText("Selected path is not a file.")
            return
        if os.name != "nt" and not os.access(candidate, os.X_OK):
            self._cli_status_label.setText("File exists but is not executable.")
            return
        self._cli_status_label.setText("Path looks valid.")
