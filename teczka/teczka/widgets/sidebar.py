"""VS Code-style sidebar activity bar for view switching."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


SIDEBAR_COLLAPSED_WIDTH = 48
SIDEBAR_EXPANDED_WIDTH = 200


class _SidebarButton(QToolButton):
    """A sidebar icon button with optional label."""

    def __init__(self, icon: QIcon, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label_text = text
        self.setIcon(icon)
        self.setIconSize(QSize(24, 24))
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setToolTip(text)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Style: transparent bg, accent left border when checked
        self.setStyleSheet("""
            QToolButton {
                border: none;
                border-left: 3px solid transparent;
                padding: 8px;
                border-radius: 0;
            }
            QToolButton:checked {
                border-left: 3px solid palette(highlight);
                background: palette(midlight);
            }
            QToolButton:hover:!checked {
                background: palette(midlight);
            }
        """)

    @property
    def label_text(self) -> str:
        return self._label_text


class Sidebar(QWidget):
    """Vertical activity bar for switching views.

    Emits view_requested(int) with the view index when a view icon is clicked.
    Emits action_requested(str) for bottom actions like "bookmarks" or "settings".
    """

    view_requested = Signal(int)  # view index (matches ActiveView enum order)
    action_requested = Signal(str)  # action name

    # View definitions: (icon_theme_name, label)
    _VIEWS = [
        ("go-home", "Home"),
        ("folder", "Folder Compare"),
        ("text-x-generic", "Text Compare"),
        ("application-octet-stream", "Hex Compare"),
        ("image-x-generic", "Image Compare"),
        ("x-office-spreadsheet", "Table Compare"),
        ("view-split-left-right", "3-Way Merge"),
    ]

    _BOTTOM_ACTIONS = [
        ("bookmark-new", "Bookmarks", "bookmarks"),
        ("configure", "Settings", "settings"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = False
        self._buttons: list[_SidebarButton] = []
        self._action_buttons: list[tuple[_SidebarButton, str]] = []
        self._build_ui()
        self.setFixedWidth(SIDEBAR_COLLAPSED_WIDTH)
        # Default to Home selected
        if self._buttons:
            self._buttons[0].setChecked(True)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        # View buttons
        for i, (icon_name, label) in enumerate(self._VIEWS):
            icon = QIcon.fromTheme(icon_name)
            btn = _SidebarButton(icon, label, self)
            btn.clicked.connect(lambda checked, idx=i: self._on_view_clicked(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch(1)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Bottom action buttons
        for icon_name, label, action_id in self._BOTTOM_ACTIONS:
            icon = QIcon.fromTheme(icon_name)
            btn = _SidebarButton(icon, label, self)
            btn.setCheckable(False)
            btn.setAutoExclusive(False)
            btn.clicked.connect(lambda checked, a=action_id: self.action_requested.emit(a))
            layout.addWidget(btn)
            self._action_buttons.append((btn, action_id))

        # Style the sidebar background
        self.setAutoFillBackground(True)

    def _on_view_clicked(self, index: int) -> None:
        self.view_requested.emit(index)

    def set_active_view(self, index: int) -> None:
        """Programmatically select a view button."""
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)

    def toggle_expanded(self) -> None:
        """Toggle between collapsed (icons only) and expanded (icons + labels) mode."""
        self._expanded = not self._expanded
        width = SIDEBAR_EXPANDED_WIDTH if self._expanded else SIDEBAR_COLLAPSED_WIDTH
        self.setFixedWidth(width)
        for btn in self._buttons:
            if self._expanded:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                btn.setText(btn.label_text)
            else:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setText("")
        for btn, _ in self._action_buttons:
            if self._expanded:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                btn.setText(btn.label_text)
            else:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setText("")

    @property
    def expanded(self) -> bool:
        return self._expanded
