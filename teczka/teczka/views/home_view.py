"""Beyond Compare-style Home/Welcome View with session type cards."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..utils.config import AppConfig


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CARD_WIDTH = 180
_CARD_HEIGHT = 140
_ICON_SIZE = 48

_SESSION_TYPES: list[dict[str, str]] = [
    {
        "label": "Folder Compare",
        "icon": "folder",
        "description": "Compare directory trees side-by-side",
    },
    {
        "label": "Text Compare",
        "icon": "text-x-generic",
        "description": "Compare text files line by line",
    },
    {
        "label": "Hex Compare",
        "icon": "application-octet-stream",
        "description": "Compare binary files byte by byte",
    },
    {
        "label": "Image Compare",
        "icon": "image-x-generic",
        "description": "Compare images with pixel analysis",
    },
]


# ---------------------------------------------------------------------------
# Session card widget
# ---------------------------------------------------------------------------


class _SessionCard(QPushButton):
    """A clickable card representing a session type."""

    def __init__(
        self,
        label: str,
        icon_name: str,
        description: str,
        index: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._index = index

        self.setFixedSize(_CARD_WIDTH, _CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)

        # Build internal layout via a child widget so QPushButton handles clicks.
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(4)

        # Icon
        icon_label = QLabel()
        icon = QIcon.fromTheme(icon_name)
        icon_label.setPixmap(icon.pixmap(QSize(_ICON_SIZE, _ICON_SIZE)))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_label)

        # Title
        title_label = QLabel(label)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        title_label.setFont(font)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        desc_font = desc_label.font()
        desc_font.setPointSize(desc_font.pointSize() - 1)
        desc_label.setFont(desc_font)
        desc_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(desc_label)

        # Style: use palette colours for a clean card look
        self.setStyleSheet(
            """
            _SessionCard {
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(base);
            }
            _SessionCard:hover {
                border: 2px solid palette(highlight);
                background: palette(alternate-base);
            }
            _SessionCard:pressed {
                background: palette(midlight);
            }
            """
        )


# ---------------------------------------------------------------------------
# HomeView
# ---------------------------------------------------------------------------


class HomeView(QWidget):
    """Welcome / landing view with session-type cards, recent sessions, and profiles."""

    session_type_selected = Signal(int)
    recent_session_selected = Signal(str, str)
    profile_selected = Signal(str)

    def __init__(self, config: Optional[AppConfig] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config

        self._build_ui()
        self._populate_recent_sessions()
        self._populate_profiles()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Container widget so the content is centred within the available space
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(24)

        # -- Welcome header --------------------------------------------------
        header = QLabel("Welcome to RCompare")
        header_font = header.font()
        header_font.setPointSize(header_font.pointSize() + 6)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(header)

        subtitle = QLabel("Select a session type to begin, or open a recent session.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(subtitle)

        # -- Session type cards (2x2 grid) ------------------------------------
        cards_group = QGroupBox("New Session")
        cards_grid = QGridLayout(cards_group)
        cards_grid.setSpacing(16)
        cards_grid.setContentsMargins(16, 24, 16, 16)

        for idx, info in enumerate(_SESSION_TYPES):
            card = _SessionCard(
                label=info["label"],
                icon_name=info["icon"],
                description=info["description"],
                index=idx,
            )
            card.clicked.connect(lambda checked=False, i=idx: self._on_card_clicked(i))
            row, col = divmod(idx, 2)
            cards_grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignCenter)

        container_layout.addWidget(cards_group)

        # -- Bottom row: Recent Sessions + Saved Profiles ---------------------
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)

        # Recent Sessions
        recent_group = QGroupBox("Recent Sessions")
        recent_layout = QVBoxLayout(recent_group)
        self._recent_list = QListWidget()
        self._recent_list.setAlternatingRowColors(True)
        self._recent_list.setMinimumHeight(120)
        self._recent_list.itemDoubleClicked.connect(self._on_recent_double_clicked)
        recent_layout.addWidget(self._recent_list)
        bottom_row.addWidget(recent_group)

        # Saved Profiles
        profiles_group = QGroupBox("Saved Profiles")
        profiles_layout = QVBoxLayout(profiles_group)
        self._profiles_list = QListWidget()
        self._profiles_list.setAlternatingRowColors(True)
        self._profiles_list.setMinimumHeight(120)
        self._profiles_list.itemDoubleClicked.connect(self._on_profile_double_clicked)
        profiles_layout.addWidget(self._profiles_list)
        bottom_row.addWidget(profiles_group)

        container_layout.addLayout(bottom_row)
        outer.addWidget(container)

    # -- Data population -----------------------------------------------------

    def _populate_recent_sessions(self) -> None:
        """Fill the recent sessions list from config."""
        self._recent_list.clear()
        if self._config is None:
            return
        for entry in self._config.recent_sessions:
            left = entry.get("left", "")
            right = entry.get("right", "")
            if not left and not right:
                continue
            display = f"{left}  <>  {right}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, (left, right))
            item.setToolTip(f"Left: {left}\nRight: {right}")
            self._recent_list.addItem(item)

        if self._recent_list.count() == 0:
            placeholder = QListWidgetItem("No recent sessions")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._recent_list.addItem(placeholder)

    def _populate_profiles(self) -> None:
        """Fill the saved profiles list from config."""
        self._profiles_list.clear()
        profiles: list[dict] = []
        if self._config is not None:
            profiles = self._config.comparison_settings.get("profiles", [])

        for profile in profiles:
            name = profile.get("name", "Untitled")
            pid = profile.get("id", name)
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            self._profiles_list.addItem(item)

        if self._profiles_list.count() == 0:
            placeholder = QListWidgetItem("No saved profiles")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._profiles_list.addItem(placeholder)

    # -- Public helpers ------------------------------------------------------

    def refresh(self, config: Optional[AppConfig] = None) -> None:
        """Reload recent sessions and profiles, optionally with a new config."""
        if config is not None:
            self._config = config
        self._populate_recent_sessions()
        self._populate_profiles()

    # -- Slots ---------------------------------------------------------------

    def _on_card_clicked(self, index: int) -> None:
        self.session_type_selected.emit(index)

    def _on_recent_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            left, right = data
            self.recent_session_selected.emit(left, right)

    def _on_profile_double_clicked(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        if pid is not None:
            self.profile_selected.emit(str(pid))
