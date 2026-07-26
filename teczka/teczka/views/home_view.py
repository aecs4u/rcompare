"""Home/Welcome view: a task launcher for every comparison type.

Three defects this file used to carry:

* the cards covered Folder/Text/Hex/Image only, and emitted an index the main
  window had to offset by one — adding Table or Merge silently opened the
  wrong view;
* ``profile_selected`` was emitted into nothing, and the profile list was read
  from ``comparison_settings["profiles"]``, a key ``ProfileManager`` never
  writes, so the section was always empty;
* the fixed 180x140 cards in a rigid 2x2 grid overflowed the content area at
  the declared 800x600 minimum.

The layout is now a responsive flow inside a scroll area, both lists come from
the services that own the data, and every entry has an explicit Open button
rather than double-click-only activation.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..utils.config import AppConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum, not fixed: cards grow with their text so translated labels and
# 125-200% display scaling do not clip.
_CARD_MIN_WIDTH = 160
_CARD_MIN_HEIGHT = 120
_ICON_SIZE = 40

# Width below which the card grid drops from three columns to two, then one.
_THREE_COLUMN_WIDTH = 720
_TWO_COLUMN_WIDTH = 480

# Stack indices in MainWindow._view_stack. Emitted directly so a new card can
# never land on the wrong view through an off-by-one offset.
_VIEW_FOLDER = 1
_VIEW_TEXT = 2
_VIEW_HEX = 3
_VIEW_IMAGE = 4
_VIEW_TABLE = 5
_VIEW_MERGE = 6

_SESSION_TYPES: list[dict] = [
    {
        "label": "Folder Compare",
        "icon": "folder",
        "fallback": icons.FOLDER_SVG,
        "description": "Compare directory trees side by side",
        "view": _VIEW_FOLDER,
    },
    {
        "label": "Text Compare",
        "icon": "text-x-generic",
        "fallback": icons.FILE_SVG,
        "description": "Compare text files line by line",
        "view": _VIEW_TEXT,
    },
    {
        "label": "Hex Compare",
        "icon": "application-octet-stream",
        "fallback": icons.FILE_SVG,
        "description": "Compare binary files byte by byte",
        "view": _VIEW_HEX,
    },
    {
        "label": "Image Compare",
        "icon": "image-x-generic",
        "fallback": icons.FILE_SVG,
        "description": "Compare images pixel by pixel, with EXIF",
        "view": _VIEW_IMAGE,
    },
    {
        "label": "Table Compare",
        "icon": "x-office-spreadsheet",
        "fallback": icons.FILE_SVG,
        "description": "Compare CSV and Excel data by row and cell",
        "view": _VIEW_TABLE,
    },
    {
        "label": "3-Way Merge",
        "icon": "view-split-left-right",
        "fallback": icons.COMPARE_SVG,
        "description": "Merge two revisions against a common base",
        "view": _VIEW_MERGE,
    },
]


# ---------------------------------------------------------------------------
# Session card widget
# ---------------------------------------------------------------------------


class _SessionCard(QPushButton):
    """A clickable card representing a comparison type."""

    def __init__(
        self,
        label: str,
        icon_name: str,
        fallback_svg: str,
        description: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self.setMinimumSize(_CARD_MIN_WIDTH, _CARD_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        # Screen readers otherwise announce an unnamed button: the title is in
        # a child QLabel, which is not the button's own accessible name.
        self.setAccessibleName(label)
        self.setAccessibleDescription(description)
        self.setToolTip(description)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(4)

        icon_label = QLabel()
        # Falls back to an embedded SVG so the card is not a blank space on a
        # session without a complete FreeDesktop icon theme.
        icon = icons.icon(icon_name, fallback_svg)
        icon_label.setPixmap(icon.pixmap(QSize(_ICON_SIZE, _ICON_SIZE)))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_label)

        title_label = QLabel(label)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setWordWrap(True)
        font = title_label.font()
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        desc_font = desc_label.font()
        desc_font.setPointSize(max(7, desc_font.pointSize() - 1))
        desc_label.setFont(desc_font)
        desc_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(desc_label)

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
            _SessionCard:focus {
                border: 2px solid palette(highlight);
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
    """Landing view with comparison-type cards, recent sessions, and profiles.

    ``session_type_selected`` carries a *view-stack index*, not a card ordinal.
    """

    session_type_selected = Signal(int)
    recent_session_selected = Signal(str, str)
    profile_selected = Signal(str)

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        parent: Optional[QWidget] = None,
        profile_manager=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._profile_manager = profile_manager
        self._cards: list[_SessionCard] = []
        self._columns = 3

        self._build_ui()
        self._populate_recent_sessions()
        self._populate_profiles()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # A scroll area is what makes the 800x600 minimum honest: content that
        # does not fit becomes scrollable instead of clipped.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        container_layout.setSpacing(12)
        scroll.setWidget(container)

        header = QLabel("Welcome to RCompare")
        header_font = header.font()
        header_font.setPointSize(header_font.pointSize() + 4)
        header_font.setBold(True)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(header)

        subtitle = QLabel(
            "Choose what to compare, or reopen a recent session or saved profile."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        container_layout.addWidget(subtitle)

        # -- Comparison type cards (responsive grid) --------------------------
        self._cards_group = QGroupBox("New Comparison")
        self._cards_grid = QGridLayout(self._cards_group)
        self._cards_grid.setSpacing(12)
        self._cards_grid.setContentsMargins(12, 18, 12, 12)

        for info in _SESSION_TYPES:
            card = _SessionCard(
                label=info["label"],
                icon_name=info["icon"],
                fallback_svg=info["fallback"],
                description=info["description"],
            )
            card.clicked.connect(
                lambda checked=False, v=info["view"]: self.session_type_selected.emit(v)
            )
            self._cards.append(card)

        container_layout.addWidget(self._cards_group)
        self._relayout_cards(self._columns)

        # -- Recent sessions + saved profiles ---------------------------------
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        recent_group = QGroupBox("Recent Sessions")
        recent_layout = QVBoxLayout(recent_group)
        self._recent_list = QListWidget()
        self._recent_list.setAlternatingRowColors(True)
        self._recent_list.setMinimumHeight(90)
        self._recent_list.setAccessibleName("Recent sessions")
        self._recent_list.itemDoubleClicked.connect(self._on_recent_activated)
        self._recent_list.currentItemChanged.connect(self._update_open_buttons)
        recent_layout.addWidget(self._recent_list)
        # Explicit affordance: double-click-only activation is undiscoverable.
        self._recent_open = QPushButton("Open Session")
        self._recent_open.setEnabled(False)
        self._recent_open.clicked.connect(
            lambda: self._on_recent_activated(self._recent_list.currentItem())
        )
        recent_layout.addWidget(self._recent_open)
        bottom_row.addWidget(recent_group)

        profiles_group = QGroupBox("Saved Profiles")
        profiles_layout = QVBoxLayout(profiles_group)
        self._profiles_list = QListWidget()
        self._profiles_list.setAlternatingRowColors(True)
        self._profiles_list.setMinimumHeight(90)
        self._profiles_list.setAccessibleName("Saved profiles")
        self._profiles_list.itemDoubleClicked.connect(self._on_profile_activated)
        self._profiles_list.currentItemChanged.connect(self._update_open_buttons)
        profiles_layout.addWidget(self._profiles_list)
        self._profile_open = QPushButton("Open Profile")
        self._profile_open.setEnabled(False)
        self._profile_open.clicked.connect(
            lambda: self._on_profile_activated(self._profiles_list.currentItem())
        )
        profiles_layout.addWidget(self._profile_open)
        bottom_row.addWidget(profiles_group)

        container_layout.addLayout(bottom_row)
        container_layout.addStretch(1)

    # -- Responsive layout ---------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        width = self.width()
        if width >= _THREE_COLUMN_WIDTH:
            columns = 3
        elif width >= _TWO_COLUMN_WIDTH:
            columns = 2
        else:
            columns = 1
        if columns != self._columns:
            self._columns = columns
            self._relayout_cards(columns)

    def _relayout_cards(self, columns: int) -> None:
        """Reflow the cards into *columns* columns."""
        for card in self._cards:
            self._cards_grid.removeWidget(card)
        for index, card in enumerate(self._cards):
            row, col = divmod(index, columns)
            self._cards_grid.addWidget(card, row, col)
        for col in range(max(3, columns)):
            self._cards_grid.setColumnStretch(col, 1 if col < columns else 0)

    # -- Data population -----------------------------------------------------

    def _populate_recent_sessions(self) -> None:
        """Fill the recent sessions list from config."""
        self._recent_list.clear()
        entries = self._config.recent_sessions if self._config is not None else []
        for entry in entries:
            left = entry.get("left", "")
            right = entry.get("right", "")
            if not left and not right:
                continue
            item = QListWidgetItem(f"{left}  ↔  {right}")
            item.setData(Qt.ItemDataRole.UserRole, (left, right))
            item.setToolTip(f"Left: {left}\nRight: {right}")
            self._recent_list.addItem(item)

        if self._recent_list.count() == 0:
            placeholder = QListWidgetItem(
                "No recent sessions yet — run a comparison to add one."
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._recent_list.addItem(placeholder)
        self._update_open_buttons()

    def _populate_profiles(self) -> None:
        """Fill the saved profiles list from ProfileManager.

        Reading ``comparison_settings["profiles"]`` here meant Home looked in a
        different store from the one ProfileManager writes, so saved profiles
        never appeared.
        """
        self._profiles_list.clear()
        profiles = (
            self._profile_manager.profiles if self._profile_manager is not None else []
        )
        for profile in profiles:
            item = QListWidgetItem(profile.name or "Untitled")
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            item.setToolTip(f"Left: {profile.left_path}\nRight: {profile.right_path}")
            self._profiles_list.addItem(item)

        if self._profiles_list.count() == 0:
            placeholder = QListWidgetItem(
                "No saved profiles — save one from Tools ▸ Profiles."
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._profiles_list.addItem(placeholder)
        self._update_open_buttons()

    def _update_open_buttons(self, *_args) -> None:
        """Enable each Open button only when its list has a real selection."""
        recent = self._recent_list.currentItem()
        self._recent_open.setEnabled(
            recent is not None and recent.data(Qt.ItemDataRole.UserRole) is not None
        )
        profile = self._profiles_list.currentItem()
        self._profile_open.setEnabled(
            profile is not None and profile.data(Qt.ItemDataRole.UserRole) is not None
        )

    # -- Public helpers ------------------------------------------------------

    def refresh(
        self, config: Optional[AppConfig] = None, profile_manager=None
    ) -> None:
        """Reload recent sessions and profiles, optionally rebinding sources."""
        if config is not None:
            self._config = config
        if profile_manager is not None:
            self._profile_manager = profile_manager
        self._populate_recent_sessions()
        self._populate_profiles()

    @property
    def recent_count(self) -> int:
        """Number of real recent entries (used by tests)."""
        return sum(
            1
            for row in range(self._recent_list.count())
            if self._recent_list.item(row).data(Qt.ItemDataRole.UserRole) is not None
        )

    @property
    def profile_count(self) -> int:
        """Number of real profile entries (used by tests)."""
        return sum(
            1
            for row in range(self._profiles_list.count())
            if self._profiles_list.item(row).data(Qt.ItemDataRole.UserRole) is not None
        )

    # -- Slots ---------------------------------------------------------------

    def _on_recent_activated(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            left, right = data
            self.recent_session_selected.emit(left, right)

    def _on_profile_activated(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        if pid is not None:
            self.profile_selected.emit(str(pid))
