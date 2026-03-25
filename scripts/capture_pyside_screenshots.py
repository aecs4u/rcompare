#!/usr/bin/env python3
"""Capture reproducible screenshots for the teczka UI."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

ROOT = Path(__file__).resolve().parents[1]
PYSIDE_ROOT = ROOT / "teczka"
if str(PYSIDE_ROOT) not in sys.path:
    sys.path.insert(0, str(PYSIDE_ROOT))

from teczka.main_window import MainWindow
from teczka.dialogs.about_dialog import AboutDialog
from teczka.dialogs.profiles_dialog import ProfilesDialog
from teczka.dialogs.settings_dialog import SettingsDialog
from teczka.dialogs.splash_dialog import SplashDialog
from teczka.dialogs.sync_dialog import SyncDialog
from teczka.models.settings import ProfileManager, SessionProfile
from teczka.utils.cli_bridge import DiffEntry, DiffStatus, FileSide, ScanReport, ScanSummary
from teczka.utils.config import AppConfig
from teczka.resources.themes import load_light_theme

OUT_DIR = ROOT / "docs" / "screenshots"


def _capture(widget: QWidget, path: Path, *, wait_ms: int = 180) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.show()
    widget.raise_()
    widget.activateWindow()
    QApplication.processEvents()
    QTest.qWait(wait_ms)
    QApplication.processEvents()
    pixmap = widget.grab()
    if not pixmap.save(str(path)):
        raise RuntimeError(f"failed to save screenshot: {path}")


def _make_png(path: Path, color: QColor, width: int = 520, height: int = 320) -> None:
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(color)
    if not img.save(str(path)):
        raise RuntimeError(f"failed to save image file: {path}")


def _build_sample_report() -> ScanReport:
    now = 1739410000
    entries = [
        DiffEntry(
            path="src/main.rs",
            status=DiffStatus.DIFFERENT,
            left=FileSide(size=3210, modified_unix=now + 20, is_dir=False),
            right=FileSide(size=3184, modified_unix=now + 10, is_dir=False),
        ),
        DiffEntry(
            path="src/lib.rs",
            status=DiffStatus.SAME,
            left=FileSide(size=1900, modified_unix=now + 5, is_dir=False),
            right=FileSide(size=1900, modified_unix=now + 5, is_dir=False),
        ),
        DiffEntry(
            path="docs/guide.md",
            status=DiffStatus.ORPHAN_LEFT,
            left=FileSide(size=2048, modified_unix=now + 30, is_dir=False),
            right=None,
        ),
        DiffEntry(
            path="scripts/deploy.sh",
            status=DiffStatus.ORPHAN_RIGHT,
            left=None,
            right=FileSide(size=800, modified_unix=now - 50, is_dir=False),
        ),
        DiffEntry(
            path="assets/logo.png",
            status=DiffStatus.DIFFERENT,
            left=FileSide(size=15800, modified_unix=now, is_dir=False),
            right=FileSide(size=16110, modified_unix=now + 40, is_dir=False),
        ),
        DiffEntry(
            path="target/cache.bin",
            status=DiffStatus.UNCHECKED,
            left=FileSide(size=4096, modified_unix=now - 5, is_dir=False),
            right=FileSide(size=4096, modified_unix=now - 5, is_dir=False),
        ),
    ]
    summary = ScanSummary(
        total=len(entries),
        same=1,
        different=2,
        orphan_left=1,
        orphan_right=1,
        unchecked=1,
    )
    return ScanReport(left="/tmp/left", right="/tmp/right", summary=summary, entries=entries)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(load_light_theme())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = _build_sample_report()

    with tempfile.TemporaryDirectory(prefix="rcompare-shots-") as td:
        tmp = Path(td)
        left_dir = tmp / "left"
        right_dir = tmp / "right"
        left_dir.mkdir(parents=True, exist_ok=True)
        right_dir.mkdir(parents=True, exist_ok=True)

        # Text compare sample files
        left_text = left_dir / "README.txt"
        right_text = right_dir / "README.txt"
        left_text.write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")
        right_text.write_text("alpha\nbeta modified\ngamma\nepsilon\n", encoding="utf-8")

        # Hex compare sample files
        left_bin = left_dir / "blob.bin"
        right_bin = right_dir / "blob.bin"
        left_bin.write_bytes(bytes(range(0, 128)))
        right_bytes = bytearray(range(0, 128))
        right_bytes[12] = 222
        right_bytes[13] = 111
        right_bytes[78] = 44
        right_bin.write_bytes(bytes(right_bytes))

        # Image compare sample files
        left_img = left_dir / "preview.png"
        right_img = right_dir / "preview.png"
        _make_png(left_img, QColor("#3a78d6"))
        _make_png(right_img, QColor("#3f88db"))

        config = AppConfig(cli_path=sys.executable, theme="light")
        config._config_file = str(tmp / "pyside-screenshot-config.json")

        window = MainWindow(config)
        window.resize(1520, 900)
        window._path_bar.left_path = str(left_dir)
        window._path_bar.right_path = str(right_dir)
        window._on_comparison_finished(report)
        window._folder_view.expand_all()
        _capture(window, OUT_DIR / "pyside_main_folder.png")

        window._text_view.compare_files(str(left_text), str(right_text))
        window._switch_view(1)
        _capture(window, OUT_DIR / "pyside_text_compare.png")

        window._hex_view.compare_files(str(left_bin), str(right_bin))
        window._switch_view(2)
        _capture(window, OUT_DIR / "pyside_hex_compare.png")

        window._image_view.compare_images(str(left_img), str(right_img))
        window._switch_view(3)
        _capture(window, OUT_DIR / "pyside_image_compare.png")

        sync = SyncDialog(window)
        sync.set_preview_source(report, str(left_dir), str(right_dir))
        _capture(sync, OUT_DIR / "pyside_sync_dialog.png")
        sync.close()

        profiles_path = tmp / "profiles.json"
        manager = ProfileManager(profiles_path)
        manager.add(
            SessionProfile(
                name="Demo Session",
                left_path=str(left_dir),
                right_path=str(right_dir),
                base_path=str(left_dir),
                ignore_patterns=["*.tmp", "target/**"],
            )
        )
        manager.add(
            SessionProfile(
                name="Images Session",
                left_path=str(left_dir / "images"),
                right_path=str(right_dir / "images"),
                base_path="",
                ignore_patterns=[],
            )
        )
        profiles = ProfilesDialog(
            manager,
            left_path=str(left_dir),
            right_path=str(right_dir),
            base_path=str(left_dir),
            ignore_patterns=["*.tmp"],
            follow_symlinks=False,
            hash_verification=True,
            parent=window,
        )
        profiles.resize(980, 620)
        _capture(profiles, OUT_DIR / "pyside_profiles_dialog.png")
        profiles.close()

        settings = SettingsDialog(config, window._settings, window)
        settings.resize(980, 660)
        _capture(settings, OUT_DIR / "pyside_options_dialog.png")
        settings.close()

        about = AboutDialog(window)
        about.resize(980, 680)
        _capture(about, OUT_DIR / "pyside_help_dialog.png")
        about.close()

        splash = SplashDialog(window)
        splash.resize(900, 560)
        _capture(splash, OUT_DIR / "pyside_splash.png")
        splash.close()

        window.close()

    print(f"screenshots saved in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
