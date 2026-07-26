"""Startup splash dialog with project overview and license access."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..icons import COMPARE_SVG, FILE_SVG, SYNC_SVG, app_icon, icon


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
    """Polished, theme-aware welcome dialog for interactive launches."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("splashDialog")
        self.setWindowTitle("Welcome to RCompare")
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumSize(700, 490)
        self.resize(740, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addWidget(self._build_description())
        root.addLayout(self._build_feature_grid(), 1)
        root.addWidget(self._build_license_panel())

        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(separator)

        footer = QHBoxLayout()
        footer.setSpacing(12)
        self._chk_hide = QCheckBox("Don't show this welcome screen again", self)
        self._chk_hide.setToolTip("You can continue to use RCompare normally on future launches.")
        footer.addWidget(self._chk_hide)
        footer.addStretch(1)

        buttons = QDialogButtonBox(self)
        self._btn_exit = buttons.addButton(
            "Exit", QDialogButtonBox.ButtonRole.RejectRole
        )
        self._btn_start = buttons.addButton(
            "Start RCompare", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._btn_start.setObjectName("primaryButton")
        self._btn_start.setMinimumWidth(138)
        self._btn_start.setDefault(True)
        self._btn_start.clicked.connect(self.accept)
        self._btn_exit.clicked.connect(self.reject)
        footer.addWidget(buttons)
        root.addLayout(footer)

        self.setStyleSheet(
            """
            QDialog#splashDialog {
                background-color: palette(window);
            }
            QFrame#hero {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 12px;
            }
            QLabel#eyebrow {
                color: palette(highlight);
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#title {
                font-size: 28px;
                font-weight: 700;
            }
            QLabel#subtitle {
                color: palette(text);
                font-size: 12px;
            }
            QLabel#intro {
                font-size: 14px;
            }
            QFrame#featureCard {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 9px;
            }
            QLabel#featureTitle {
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#featureText, QLabel#licenseText {
                color: palette(text);
            }
            QFrame#licensePanel {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
            }
            QPushButton#licenseButton {
                border: none;
                color: palette(highlight);
                font-weight: 600;
                padding: 4px 6px;
            }
            QPushButton#licenseButton:hover {
                text-decoration: underline;
            }
            QPushButton#primaryButton {
                min-height: 28px;
                padding: 4px 14px;
                font-weight: 600;
            }
            """
        )

    def should_show_again(self) -> bool:
        """Return False if the user asked not to see the splash again."""
        return not self._chk_hide.isChecked()

    def _build_header(self) -> QWidget:
        hero = QFrame(self)
        hero.setObjectName("hero")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(18)

        mark = QLabel(hero)
        mark.setFixedSize(72, 72)
        mark.setPixmap(app_icon().pixmap(64, 64))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setAccessibleName("RCompare application icon")
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        eyebrow = QLabel("WELCOME", hero)
        eyebrow.setObjectName("eyebrow")
        title = QLabel("RCompare", hero)
        title.setObjectName("title")
        app = QApplication.instance()
        version = app.applicationVersion() if app is not None else "0.1.0"
        subtitle = QLabel(
            f"Version {version}  ·  High-performance file and folder comparison",
            hero,
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        text_col.addWidget(eyebrow)
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        layout.addLayout(text_col, 1)
        return hero

    def _build_description(self) -> QWidget:
        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(4, 0, 4, 0)
        body = QLabel(
            "See exactly what changed, review content with purpose-built viewers, "
            "and keep folders in sync with confidence.",
            box,
        )
        body.setObjectName("intro")
        body.setWordWrap(True)
        layout.addWidget(body)
        return box

    def _build_feature_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        features = (
            (
                "folder-sync",
                COMPARE_SVG,
                "Compare at a glance",
                "Scan large folder trees quickly and focus on meaningful differences.",
            ),
            (
                "text-x-generic",
                FILE_SVG,
                "Review every format",
                "Inspect text, tables, images, and binary files in dedicated views.",
            ),
            (
                "folder-copy",
                SYNC_SVG,
                "Sync with control",
                "Copy selected changes or synchronize complete folders with a clear plan.",
            ),
        )
        for column, feature in enumerate(features):
            grid.addWidget(self._build_feature_card(*feature), 0, column)
            grid.setColumnStretch(column, 1)
        return grid

    def _build_feature_card(
        self,
        icon_name: str,
        fallback_svg: str,
        title_text: str,
        body_text: str,
    ) -> QWidget:
        card = QFrame(self)
        card.setObjectName("featureCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(9)

        feature_icon = QLabel(card)
        feature_icon.setPixmap(icon(icon_name, fallback_svg).pixmap(30, 30))
        feature_icon.setFixedSize(32, 32)
        feature_icon.setAccessibleName(f"{title_text} icon")

        title = QLabel(title_text, card)
        title.setObjectName("featureTitle")
        body = QLabel(body_text, card)
        body.setObjectName("featureText")
        body.setWordWrap(True)
        body.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        layout.addWidget(feature_icon)
        layout.addWidget(title)
        layout.addWidget(body, 1)
        return card

    def _build_license_panel(self) -> QWidget:
        box = QFrame(self)
        box.setObjectName("licensePanel")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(8)

        title = QLabel("<b>Open source</b>", box)
        text = QLabel(
            "RCompare is distributed under the MIT License.",
            box,
        )
        text.setObjectName("licenseText")
        btn_open = QPushButton("View license", box)
        btn_open.setObjectName("licenseButton")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self._open_license_dialog)

        layout.addWidget(title)
        layout.addWidget(text)
        layout.addStretch(1)
        layout.addWidget(btn_open)
        return box

    def _open_license_dialog(self) -> None:
        dialog = LicenseDialog(self)
        dialog.exec()
