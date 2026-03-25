"""QApplication setup and entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .dialogs.splash_dialog import SplashDialog
from .main_window import MainWindow
from .utils.config import AppConfig
from .logger import setup_logging, get_logger

log = get_logger("app")


def launch(
    left: str | None = None,
    right: str | None = None,
    log_level: str = "INFO",
    log_file: str | None = None,
) -> None:
    """Launch the teczka GUI application."""
    setup_logging(log_level=log_level, log_file=log_file)
    log.info("starting teczka app")

    app = QApplication(sys.argv)
    app.setApplicationName("RCompare")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("aecs4u")
    app.setStyle("Fusion")

    config = AppConfig.load()
    log.info("configuration loaded", theme=config.theme)

    # Pre-populate paths from CLI args
    if left:
        config.last_paths["left"] = left
    if right:
        config.last_paths["right"] = right

    # KDE Compliance: Respect system theme (Breeze Light/Dark on KDE Plasma)

    splash = SplashDialog()
    if splash.exec() != SplashDialog.DialogCode.Accepted:
        log.info("startup cancelled by user from splash")
        return

    try:
        window = MainWindow(config)
    except Exception:
        log.exception("main window creation failed")
        raise

    # Restore window geometry
    geom = config.window_geometry
    if geom.get("width") and geom.get("height"):
        window.resize(geom["width"], geom["height"])
    if geom.get("x") is not None and geom.get("y") is not None:
        window.move(geom["x"], geom["y"])
    else:
        window.resize(1200, 800)

    window.show()
    log.info("main window shown")
    sys.exit(app.exec())
