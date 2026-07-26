"""QApplication setup and entry point."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from . import icons
from .dialogs.splash_dialog import SplashDialog
from .main_window import MainWindow
from .resources.themes import apply_theme, normalize_theme
from .utils.config import AppConfig
from .logger import setup_logging, get_logger

log = get_logger("app")


def _should_show_splash(
    config: AppConfig,
    left: str | None,
    right: str | None,
) -> bool:
    """Return whether this launch should stop at the welcome dialog.

    File-manager and command-line launches must never be blocked by a modal
    welcome screen. Supplying either path is enough to identify that flow.
    """
    return config.show_splash and left is None and right is None


def launch(
    left: str | None = None,
    right: str | None = None,
    log_level: str = "INFO",
    log_file: str | None = None,
) -> None:
    """Launch the teczka GUI application."""
    setup_logging(log_level=log_level, log_file=log_file)
    log.info("starting teczka app")

    # Prefer the XDG desktop portal for native dialogs when the session
    # provides one. On KDE/GNOME this gives the system file chooser, whose
    # Network sidebar is how users reach SFTP/SMB/WebDAV shares. Only set it
    # when the user hasn't chosen a theme themselves.
    if not os.environ.get("QT_QPA_PLATFORMTHEME") and os.environ.get(
        "XDG_CURRENT_DESKTOP"
    ):
        os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"

    app = QApplication(sys.argv)
    app.setApplicationName("RCompare")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("aecs4u")
    app.setDesktopFileName("org.aecs4u.rcompare")
    # Falls back to an embedded SVG, so the window/taskbar entry is never blank
    # on a session without a complete FreeDesktop icon theme.
    app.setWindowIcon(icons.app_icon())

    config = AppConfig.load()
    log.info("configuration loaded", theme=config.theme)

    # Pre-populate paths from CLI args
    if left:
        config.last_paths["left"] = left
    if right:
        config.last_paths["right"] = right

    # Apply the configured theme before the first window is constructed.
    #
    # The Light/Dark selector was exposed in Settings but neither stylesheet
    # was ever loaded, at startup or on change, so the choice did nothing. The
    # "system" default applies no stylesheet at all, which is what lets Plasma
    # dark mode, the user's accent colour and high-contrast schemes through.
    config.theme = normalize_theme(config.theme)
    apply_theme(app, config.theme)
    log.info("theme applied", theme=config.theme)


    # The splash is a courtesy, not a gate: it is skipped when the caller
    # already said what to compare, and the "don't show again" choice is
    # persisted even if the user then exits from the dialog.
    if _should_show_splash(config, left, right):
        splash = SplashDialog()
        result = splash.exec()
        show_again = splash.should_show_again()
        if config.show_splash != show_again:
            config.show_splash = show_again
            config.save()
            log.info("splash preference updated", show_splash=show_again)
        if result != SplashDialog.DialogCode.Accepted:
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
