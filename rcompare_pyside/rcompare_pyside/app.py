"""QApplication setup and entry point."""

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from .main_window import MainWindow
from .utils.config import AppConfig
from .resources.themes import load_light_theme, load_dark_theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RCompare")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("aecs4u")
    app.setStyle("Fusion")

    config = AppConfig.load()

    if config.theme == "dark":
        app.setStyleSheet(load_dark_theme())
    else:
        app.setStyleSheet(load_light_theme())

    window = MainWindow(config)

    # Restore window geometry
    geom = config.window_geometry
    if geom.get("width") and geom.get("height"):
        window.resize(geom["width"], geom["height"])
    if geom.get("x") is not None and geom.get("y") is not None:
        window.move(geom["x"], geom["y"])
    else:
        window.resize(1200, 800)

    window.show()
    sys.exit(app.exec())
