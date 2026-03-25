"""KDE Plasma Human Interface Guidelines constants and helpers.

Based on Kirigami spacing units and KDE HIG recommendations.
See: https://develop.kde.org/hig/
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget


# Kirigami spacing units (px at 96 DPI)
SMALL_SPACING = 4
MEDIUM_SPACING = 6
LARGE_SPACING = 8
GRID_UNIT = 18

# Standard margins and padding
DIALOG_MARGIN = LARGE_SPACING * 2    # 16px
GROUP_SPACING = LARGE_SPACING * 3    # 24px
SECTION_SPACING = LARGE_SPACING * 4  # 32px

# Icon sizes (matching Breeze icon theme)
ICON_SMALL = 16
ICON_SMALL_MEDIUM = 22
ICON_MEDIUM = 32
ICON_LARGE = 48
ICON_HUGE = 64

# Standard widget sizes
SIDEBAR_MIN_WIDTH = 200
SIDEBAR_MAX_WIDTH = 300
TOOLBAR_HEIGHT = 40
STATUSBAR_HEIGHT = 24
PATHBAR_HEIGHT = 32

# Progress bar
PROGRESS_HEIGHT = 20
PROGRESS_OVERALL_HEIGHT = 16


def dpi_scale(px: int, widget: QWidget | None = None) -> int:
    """Scale pixel value for current DPI.

    Uses the widget's device pixel ratio if provided,
    otherwise falls back to the primary screen.
    """
    if widget is not None:
        ratio = widget.devicePixelRatioF()
    else:
        app = QApplication.instance()
        if app and app.primaryScreen():
            ratio = app.primaryScreen().devicePixelRatio()
        else:
            ratio = 1.0
    return round(px * ratio)


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string (KDE-style)."""
    if size_bytes < 0:
        return "Unknown"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KiB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MiB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GiB"


def format_count(count: int) -> str:
    """Format large numbers with locale-appropriate separators."""
    return f"{count:,}"


def format_duration(seconds: float) -> str:
    """Format elapsed time as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h{mins:02d}m"
