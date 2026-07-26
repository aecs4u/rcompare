"""Settings dialog for RCompare."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor, QFontDatabase, QIcon

from ..models.settings import ComparisonSettings
from ..resources.themes import THEME_NAMES, normalize_theme
from ..utils.config import AppConfig


# (label, CLI value) for --ignore-whitespace. The value is what
# rcompare_cli's WhitespaceModeArg accepts.
_WHITESPACE_MODES: tuple[tuple[str, str], ...] = (
    ("None", "none"),
    ("All", "all"),
    ("Leading", "leading"),
    ("Trailing", "trailing"),
    ("Changes", "changes"),
)

_DEFAULT_BINARY_PATTERNS: tuple[str, ...] = (
    "*.exe", "*.dll", "*.so", "*.dylib", "*.bin", "*.dat", "*.o", "*.a", "*.lib",
)

_THEME_LABELS: tuple[tuple[str, str], ...] = (
    ("Follow system", "system"),
    ("Light", "light"),
    ("Dark", "dark"),
)
assert {value for _, value in _THEME_LABELS} == set(THEME_NAMES)


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
        self._build_files_tab()
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
        saved_diff = self._config.diff_options

        ws_group = QGroupBox("Whitespace Handling")
        ws_layout = QFormLayout(ws_group)
        self._ws_combo = QComboBox()
        for label, value in _WHITESPACE_MODES:
            self._ws_combo.addItem(label, value)
        ws_index = self._ws_combo.findData(
            str(saved_diff.get("ignore_whitespace", "none"))
        )
        self._ws_combo.setCurrentIndex(max(0, ws_index))
        ws_layout.addRow("Ignore whitespace:", self._ws_combo)
        layout.addWidget(ws_group)

        # Text comparison options
        text_group = QGroupBox("Text Comparison")
        text_layout = QVBoxLayout(text_group)
        self._case_check = QCheckBox("Ignore case differences")
        self._case_check.setChecked(bool(saved_diff.get("ignore_case", False)))
        text_layout.addWidget(self._case_check)
        self._text_diff_check = QCheckBox("Enable line-by-line text diff")
        self._text_diff_check.setChecked(bool(saved_diff.get("text_diff", True)))
        text_layout.addWidget(self._text_diff_check)
        layout.addWidget(text_group)

        # Specialized comparisons
        spec_group = QGroupBox("Specialized Comparisons")
        spec_layout = QVBoxLayout(spec_group)
        self._image_diff_check = QCheckBox("Enable pixel-level image comparison")
        self._image_diff_check.setChecked(bool(saved_diff.get("image_diff", False)))
        spec_layout.addWidget(self._image_diff_check)
        self._image_exif_check = QCheckBox("Compare EXIF metadata between images")
        self._image_exif_check.setChecked(bool(saved_diff.get("image_exif", False)))
        self._image_exif_check.setToolTip(
            "Shows differing camera, lens, timestamp and exposure tags in Image Compare."
        )
        spec_layout.addWidget(self._image_exif_check)
        self._csv_diff_check = QCheckBox("Enable CSV row-by-row comparison")
        self._csv_diff_check.setChecked(bool(saved_diff.get("csv_diff", False)))
        spec_layout.addWidget(self._csv_diff_check)
        self._json_diff_check = QCheckBox("Enable JSON/YAML structural comparison")
        self._json_diff_check.setChecked(bool(saved_diff.get("json_diff", False)))
        spec_layout.addWidget(self._json_diff_check)
        self._excel_diff_check = QCheckBox("Enable Excel sheet/cell comparison")
        self._excel_diff_check.setChecked(bool(saved_diff.get("excel_diff", False)))
        spec_layout.addWidget(self._excel_diff_check)
        layout.addWidget(spec_group)

        # CSV key columns -- the row-alignment fix (WI-5.3). Without a key,
        # CSV rows are paired by position, so one inserted row reports every
        # later row as "different".
        csv_group = QGroupBox("CSV Row Alignment")
        csv_layout = QFormLayout(csv_group)
        self._csv_key_edit = QLineEdit(
            ", ".join(saved_diff.get("csv_key_columns", []) or [])
        )
        self._csv_key_edit.setPlaceholderText("id, order_number  (blank = align by position)")
        csv_layout.addRow("Key columns:", self._csv_key_edit)
        csv_hint = QLabel(
            "Comma-separated header names. With a key, rows are matched by "
            "value instead of by position, so inserted or reordered rows are "
            "reported as added/removed rather than as differences."
        )
        csv_hint.setWordWrap(True)
        csv_layout.addRow(csv_hint)
        layout.addWidget(csv_group)

        # Regex rules
        regex_group = QGroupBox("Regex Normalization Rules")
        regex_layout = QVBoxLayout(regex_group)
        regex_hint = QLabel("Format: pattern:replacement:description (one per line)")
        regex_hint.setWordWrap(True)
        self._regex_edit = QTextEdit()
        self._regex_edit.setMinimumHeight(80)
        self._regex_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._regex_edit.setPlainText("\n".join(saved_diff.get("regex_rules", [])))
        self._regex_edit.setPlaceholderText(
            r"\d{4}-\d{2}-\d{2}:[DATE]:Normalize dates"
        )
        regex_layout.addWidget(regex_hint)
        regex_layout.addWidget(self._regex_edit)
        layout.addWidget(regex_group, 1)

        self._tabs.addTab(tab, self._icon("text-x-generic"), "Diff Options")

    def _build_files_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # File encoding
        encoding_group = QGroupBox("File Encoding")
        encoding_layout = QFormLayout(encoding_group)
        self._encoding_combo = QComboBox()
        self._encoding_combo.setEditable(True)
        self._encoding_combo.addItems([
            "utf-8", "utf-16", "ascii", "latin-1", "iso-8859-1",
            "iso-8859-15", "cp1252", "shift_jis", "euc-jp", "gb2312",
            "big5", "koi8-r",
        ])
        self._encoding_combo.setCurrentText(
            str(self._config.file_options.get("encoding", "utf-8"))
        )
        encoding_layout.addRow("Default encoding:", self._encoding_combo)
        encoding_hint = QLabel(
            "Encoding used when reading text files for comparison. "
            "Files with BOM markers are auto-detected."
        )
        encoding_hint.setWordWrap(True)
        encoding_layout.addRow(encoding_hint)
        layout.addWidget(encoding_group)

        # Line endings
        eol_group = QGroupBox("Line Endings")
        eol_layout = QVBoxLayout(eol_group)
        self._eol_ignore_check = QCheckBox("Ignore line ending differences (LF vs CRLF)")
        self._eol_ignore_check.setChecked(
            bool(self._config.file_options.get("ignore_eol", True))
        )
        eol_layout.addWidget(self._eol_ignore_check)
        layout.addWidget(eol_group)

        # File type filters
        filter_group = QGroupBox("Binary File Detection")
        filter_layout = QVBoxLayout(filter_group)
        filter_hint = QLabel(
            "Files matching these patterns are always opened in hex view. "
            "One glob pattern per line."
        )
        filter_hint.setWordWrap(True)
        self._binary_patterns_edit = QTextEdit()
        self._binary_patterns_edit.setMinimumHeight(80)
        self._binary_patterns_edit.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self._binary_patterns_edit.setPlainText(
            "\n".join(
                self._config.file_options.get("binary_patterns", _DEFAULT_BINARY_PATTERNS)
            )
        )
        filter_layout.addWidget(filter_hint)
        filter_layout.addWidget(self._binary_patterns_edit)
        layout.addWidget(filter_group, 1)

        self._tabs.addTab(tab, self._icon("folder-open"), "Files")

    def _build_appearance_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        appearance_group = QGroupBox("Theme")
        appearance_layout = QFormLayout(appearance_group)
        self._theme_combo = QComboBox()
        for label, value in _THEME_LABELS:
            self._theme_combo.addItem(label, value)
        theme_index = self._theme_combo.findData(normalize_theme(self._config.theme))
        self._theme_combo.setCurrentIndex(max(0, theme_index))
        self._theme_hint = QLabel("")
        self._theme_hint.setWordWrap(True)
        self._theme_combo.currentTextChanged.connect(self._update_theme_hint)
        self._update_theme_hint(self._theme_combo.currentText())
        appearance_layout.addRow("Color theme:", self._theme_combo)
        appearance_layout.addRow(self._theme_hint)
        layout.addWidget(appearance_group)

        # Diff colors (Kompare ViewPage style)
        colors_group = QGroupBox("Diff Colors")
        colors_layout = QFormLayout(colors_group)

        saved = self._config.appearance
        self._color_buttons: dict[str, QPushButton] = {}
        color_defs = [
            ("color_added", "Added lines:", "#c8e6c9"),
            ("color_removed", "Removed lines:", "#ffcdd2"),
            ("color_changed", "Changed lines:", "#fff9c4"),
            ("color_applied", "Applied changes:", "#e0e0e0"),
        ]
        for key, label, default in color_defs:
            btn = QPushButton()
            btn.setFixedSize(60, 24)
            color = QColor(saved.get(key, default))
            btn.setStyleSheet(f"background-color: {color.name()};")
            btn.setProperty("color", color.name())
            btn.clicked.connect(lambda checked=False, b=btn, k=key: self._pick_color(b))
            self._color_buttons[key] = btn
            colors_layout.addRow(label, btn)

        layout.addWidget(colors_group)

        # Font settings
        font_group = QGroupBox("Diff Font")
        font_layout = QFormLayout(font_group)
        self._font_combo = QFontComboBox()
        saved_font = saved.get("font_family")
        if saved_font:
            from PySide6.QtGui import QFont
            self._font_combo.setCurrentFont(QFont(saved_font))
        else:
            self._font_combo.setCurrentFont(
                QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
            )
        font_layout.addRow("Font:", self._font_combo)
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(6, 72)
        self._font_size_spin.setValue(int(saved.get("font_size", 10)))
        font_layout.addRow("Size:", self._font_size_spin)
        self._tab_width_spin = QSpinBox()
        self._tab_width_spin.setRange(1, 16)
        self._tab_width_spin.setValue(int(saved.get("tab_width", 4)))
        font_layout.addRow("Tab width:", self._tab_width_spin)
        layout.addWidget(font_group)

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

    def _update_theme_hint(self, _theme_name: str = "") -> None:
        theme = self._theme_combo.currentData()
        if theme == "system":
            self._theme_hint.setText(
                "Uses the desktop palette, including Plasma dark mode, your "
                "accent colour and high-contrast schemes."
            )
        else:
            self._theme_hint.setText(
                f"The {theme} stylesheet is applied immediately when you click OK."
            )

    def get_settings(self) -> ComparisonSettings:
        patterns = [p.strip() for p in self._patterns_edit.toPlainText().splitlines() if p.strip()]
        diff = self.get_diff_options()
        return ComparisonSettings(
            ignore_patterns=patterns,
            follow_symlinks=self._symlinks_check.isChecked(),
            use_hash_verification=self._hash_check.isChecked(),
            cache_dir=self._cache_edit.text() or None,
            text_diff=bool(diff["text_diff"]),
            ignore_whitespace=str(diff["ignore_whitespace"]),
            ignore_case=bool(diff["ignore_case"]),
            regex_rules=list(diff["regex_rules"]),
            image_diff=bool(diff["image_diff"]),
            csv_diff=bool(diff["csv_diff"]),
            json_diff=bool(diff["json_diff"]),
            excel_diff=bool(diff["excel_diff"]),
        )

    def get_appearance_settings(self) -> dict:
        """Return appearance settings (colors, font, tab width)."""
        result: dict = {}
        for key, btn in self._color_buttons.items():
            result[key] = btn.property("color")
        result["font_family"] = self._font_combo.currentFont().family()
        result["font_size"] = self._font_size_spin.value()
        result["tab_width"] = self._tab_width_spin.value()
        return result

    def get_config_updates(self) -> dict:
        return {
            "theme": normalize_theme(self._theme_combo.currentData()),
            "cli_path": self._cli_edit.text().strip() or None,
        }

    def get_diff_options(self) -> dict:
        """Return the Diff Options page.

        Every control here used to be decoration: ``get_settings()`` returned
        only ignore patterns, symlink/hash and cache, so whitespace, case,
        specialised comparisons and regex rules were collected and dropped.
        """
        rules = [
            line.strip()
            for line in self._regex_edit.toPlainText().splitlines()
            if line.strip()
        ]
        keys = [
            part.strip()
            for part in self._csv_key_edit.text().split(",")
            if part.strip()
        ]
        return {
            "ignore_whitespace": self._ws_combo.currentData(),
            "ignore_case": self._case_check.isChecked(),
            "text_diff": self._text_diff_check.isChecked(),
            "image_diff": self._image_diff_check.isChecked(),
            "image_exif": self._image_exif_check.isChecked(),
            "csv_diff": self._csv_diff_check.isChecked(),
            "csv_key_columns": keys,
            "json_diff": self._json_diff_check.isChecked(),
            "yaml_diff": self._json_diff_check.isChecked(),
            "excel_diff": self._excel_diff_check.isChecked(),
            "regex_rules": rules,
        }

    def get_file_options(self) -> dict:
        """Return the Files page (encoding, EOL handling, binary patterns)."""
        patterns = [
            line.strip()
            for line in self._binary_patterns_edit.toPlainText().splitlines()
            if line.strip()
        ]
        return {
            "encoding": self._encoding_combo.currentText().strip() or "utf-8",
            "ignore_eol": self._eol_ignore_check.isChecked(),
            "binary_patterns": patterns,
        }

    def accept(self) -> None:
        """Validate before closing.

        An unusable CLI path used to be accepted silently and only surfaced
        much later as a failed comparison.
        """
        problem = self._cli_path_problem()
        if problem is not None:
            answer = QMessageBox.warning(
                self,
                "CLI Path Not Usable",
                f"{problem}\n\nSave anyway? Comparison will not work until "
                "a valid rcompare_cli binary is configured.",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Save:
                self._tabs.setCurrentIndex(self._tabs.count() - 1)
                self._cli_edit.setFocus()
                return
        super().accept()

    def _cli_path_problem(self) -> str | None:
        """Return why the configured CLI path is unusable, or None."""
        raw = self._cli_edit.text().strip()
        if not raw:
            return None  # empty means auto-detect, which is legitimate
        candidate = Path(raw)
        if not candidate.exists():
            return f"'{raw}' does not exist."
        if not candidate.is_file():
            return f"'{raw}' is not a file."
        if os.name != "nt" and not os.access(candidate, os.X_OK):
            return f"'{raw}' is not executable."
        return None

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
        self._theme_combo.setCurrentIndex(self._theme_combo.findData("system"))
        self._ws_combo.setCurrentIndex(self._ws_combo.findData("none"))
        self._case_check.setChecked(False)
        self._text_diff_check.setChecked(True)
        self._image_diff_check.setChecked(False)
        self._image_exif_check.setChecked(False)
        self._csv_diff_check.setChecked(False)
        self._json_diff_check.setChecked(False)
        self._excel_diff_check.setChecked(False)
        self._csv_key_edit.clear()
        self._regex_edit.clear()
        self._encoding_combo.setCurrentText("utf-8")
        self._eol_ignore_check.setChecked(True)
        self._binary_patterns_edit.setPlainText("\n".join(_DEFAULT_BINARY_PATTERNS))
        # Reset diff colors
        defaults = {
            "color_added": "#c8e6c9",
            "color_removed": "#ffcdd2",
            "color_changed": "#fff9c4",
            "color_applied": "#e0e0e0",
        }
        for key, btn in self._color_buttons.items():
            color = defaults.get(key, "#ffffff")
            btn.setStyleSheet(f"background-color: {color};")
            btn.setProperty("color", color)
        # Reset font settings
        self._font_combo.setCurrentFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self._font_size_spin.setValue(10)
        self._tab_width_spin.setValue(4)
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

    def _pick_color(self, button: QPushButton) -> None:
        current = QColor(button.property("color"))
        color = QColorDialog.getColor(current, self, "Select Color")
        if color.isValid():
            button.setStyleSheet(f"background-color: {color.name()};")
            button.setProperty("color", color.name())

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
