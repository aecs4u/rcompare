"""QApplication setup and entry point."""

import sys

from PySide6.QtWidgets import QApplication

from .dialogs.splash_dialog import SplashDialog
from .main_window import MainWindow
from .utils.config import AppConfig
from .resources.themes import load_light_theme, load_dark_theme
from .utils.telemetry import configure_telemetry, log_exception, log_info


def main():
    configure_telemetry()
    log_info("starting rcompare_pyside app")

    app = QApplication(sys.argv)
    app.setApplicationName("RCompare")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("aecs4u")
    app.setStyle("Fusion")

    config = AppConfig.load()
    log_info("configuration loaded", theme=config.theme)

    # KDE Compliance: Respect system theme instead of forcing custom stylesheet
    # Custom themes are available but disabled by default for KDE integration
    # To enable custom themes, set config.theme to "light" or "dark" explicitly
    # and uncomment the code below:
    #
    # if config.theme == "dark":
    #     app.setStyleSheet(load_dark_theme())
    # elif config.theme == "light":
    #     app.setStyleSheet(load_light_theme())
    #
    # By default, use system theme (Breeze Light/Dark on KDE Plasma)

    splash = SplashDialog()
    if splash.exec() != SplashDialog.DialogCode.Accepted:
        log_info("startup cancelled by user from splash")
        return

    try:
        window = MainWindow(config)
    except Exception:
        log_exception("main window creation failed")
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
    log_info("main window shown")
    sys.exit(app.exec())
