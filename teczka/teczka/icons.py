"""XDG-compliant icon resource manager for Teczka.

Provides FreeDesktop theme icon lookup with embedded SVG fallbacks so that
essential toolbar/menu icons are always available even when the active icon
theme is incomplete.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# ---------------------------------------------------------------------------
# Icon size constants (matches KDE/FreeDesktop conventions)
# ---------------------------------------------------------------------------

ICON_SMALL: int = 16
ICON_MEDIUM: int = 22
ICON_LARGE: int = 32
ICON_XLARGE: int = 48

# ---------------------------------------------------------------------------
# Embedded SVG fallback constants
#
# Each SVG uses a 24x24 viewBox and ``currentColor`` so that it automatically
# adapts to the active widget palette (light *or* dark theme).
# ---------------------------------------------------------------------------

COMPARE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="2" y="4" width="8" height="14" rx="1"/>'
    '<rect x="14" y="6" width="8" height="14" rx="1"/>'
    '</svg>'
)

SWAP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="17 1 21 5 17 9"/><line x1="3" y1="5" x2="21" y2="5"/>'
    '<polyline points="7 23 3 19 7 15"/><line x1="21" y1="19" x2="3" y2="19"/>'
    '</svg>'
)

FOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
    '</svg>'
)

FILE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<polyline points="14 2 14 8 20 8"/>'
    '</svg>'
)

SYNC_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="23 4 23 10 17 10"/>'
    '<polyline points="1 20 1 14 7 14"/>'
    '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/>'
    '<path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14"/>'
    '</svg>'
)

STOP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="3" y="3" width="18" height="18" rx="2"/>'
    '</svg>'
)

SETTINGS_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="3"/>'
    '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06'
    'a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09'
    'A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83'
    'l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09'
    'A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83'
    'l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09'
    'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83'
    'l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09'
    'a1.65 1.65 0 0 0-1.51 1z"/>'
    '</svg>'
)

BOOKMARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 '
    '5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'
    '</svg>'
)

COPY_LEFT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="19" y1="12" x2="5" y2="12"/>'
    '<polyline points="12 19 5 12 12 5"/>'
    '</svg>'
)

COPY_RIGHT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="5" y1="12" x2="19" y2="12"/>'
    '<polyline points="12 5 19 12 12 19"/>'
    '</svg>'
)

DELETE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="3 6 5 6 21 6"/>'
    '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4'
    'a2 2 0 0 1 2 2v2"/>'
    '</svg>'
)

EXPORT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    '<polyline points="7 10 12 15 17 10"/>'
    '<line x1="12" y1="15" x2="12" y2="3"/>'
    '</svg>'
)

# Application icon SVG (two overlapping documents with a delta symbol)
_APP_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="2" y="3" width="9" height="16" rx="1"/>'
    '<rect x="13" y="5" width="9" height="16" rx="1"/>'
    '<path d="M6 9l3 5H5z" fill="currentColor" stroke="none"/>'
    '</svg>'
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _svg_to_icon(svg_data: str) -> QIcon:
    """Render an SVG string into a *QIcon* at multiple standard sizes.

    Returns an empty icon when no ``QGuiApplication`` exists: QPixmap requires
    one, and creating pixmaps without it aborts the process rather than
    raising.
    """
    icon = QIcon()
    if QGuiApplication.instance() is None:
        return icon
    data = QByteArray(svg_data.encode("utf-8"))
    renderer = QSvgRenderer(data)
    if not renderer.isValid():
        return icon
    for size in (ICON_SMALL, ICON_MEDIUM, ICON_LARGE, ICON_XLARGE):
        qsize = QSize(size, size)
        image = QImage(qsize, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(QPixmap.fromImage(image))
    return icon


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def icon(name: str, fallback_svg: str | None = None) -> QIcon:
    """Look up a FreeDesktop theme icon, falling back to an embedded SVG.

    Parameters
    ----------
    name:
        XDG icon name (e.g. ``"document-open"``, ``"edit-copy"``).
    fallback_svg:
        Optional SVG string used when the system theme does not provide
        *name*.  When *None* the function returns an empty ``QIcon`` on
        miss.
    """
    theme_icon = QIcon.fromTheme(name)
    if not theme_icon.isNull():
        return theme_icon
    if fallback_svg is not None:
        return _svg_to_icon(fallback_svg)
    return QIcon()


def first_available(*names: str, fallback_svg: str | None = None) -> QIcon:
    """Return the first theme icon among *names*, else the embedded fallback.

    Several XDG icon names mean the same thing across themes (Breeze uses
    ``object-flip-horizontal`` where others use ``view-sort-descending``), so
    call sites usually want to try a list before giving up.
    """
    for name in names:
        theme_icon = QIcon.fromTheme(name)
        if not theme_icon.isNull():
            return theme_icon
    if fallback_svg is not None:
        return _svg_to_icon(fallback_svg)
    return QIcon()


def from_svg(svg_data: str) -> QIcon:
    """Render an SVG string into a QIcon at the standard icon sizes."""
    return _svg_to_icon(svg_data)


def app_icon() -> QIcon:
    """Return the application icon, preferring the XDG theme entry."""
    theme_icon = QIcon.fromTheme("org.aecs4u.rcompare")
    if not theme_icon.isNull():
        return theme_icon
    return _svg_to_icon(_APP_ICON_SVG)
