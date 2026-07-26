"""Main application window -- central orchestrator for the RCompare PySide6 frontend."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fnmatch import fnmatch
import os
from pathlib import Path
import shutil
from typing import Optional

from PySide6.QtCore import Qt, QMimeData, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .utils.config import AppConfig
from .utils.cli_bridge import CliBridge, DiffStatus, ScanReport
from .utils.path_picker import pick_folder
from .utils.safe_paths import (
    UnsafePathError,
    resolve_safe_relative,
    validate_child_name,
)
from .models.comparison import build_tree_with_options, TreeNode
from .models.filter_state import (
    DIFF_OPTION_MODES,
    FolderFilterState,
    PRESET_ALL,
    PRESET_DIFFS,
    PRESET_SAME,
)
from .models.settings import ComparisonSettings, ProfileManager
from .resources.themes import apply_theme
from .shortcuts import collect_shortcuts, standard_key
from .state import ActiveView, AppState
from .views.folder_view import FolderView
from .views.text_view import TextView
from .views.hex_view import HexView
from .views.image_view import ImageView
from .views.home_view import HomeView
from .widgets.document_tab_bar import DocumentTabBar
from .widgets.sidebar import Sidebar
from .widgets.session_tab_bar import SessionTabBar
from .widgets.compact_path_bar import CompactPathBar
from .widgets.integrated_status_bar import IntegratedStatusBar
from .workers.comparison_worker import ComparisonResult, ComparisonWorker, CliJsonWorker
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.sync_dialog import SyncDialog
from .dialogs.profiles_dialog import ProfilesDialog
from .dialogs.about_dialog import AboutDialog
from .dialogs.stats_dialog import StatsDialog
from .models.undo_stack import OperationHistory, Operation, create_backup
from .utils.telemetry import log_error, log_info, log_warning

# ---------------------------------------------------------------------------
# File-type extension sets used for view switching on double-click
# ---------------------------------------------------------------------------
TEXT_EXTENSIONS = {
    ".txt", ".md", ".rs", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".c", ".cpp", ".h", ".hpp", ".java", ".go", ".rb", ".php",
    ".sh", ".css", ".html", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".sql", ".log",
}

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif",
    ".webp", ".ico", ".svg",
}

TABLE_EXTENSIONS = {
    ".csv", ".tsv", ".xlsx", ".xls",
}

_AUTO_CLOSE_PROFILE_NAME = "Last Session (Auto)"

# Stack indices of the permanent views. Anything at or beyond
# _BASE_VIEW_COUNT is a dynamically opened comparison document.
VIEW_HOME = 0
VIEW_FOLDER = 1
VIEW_TEXT = 2
VIEW_HEX = 3
VIEW_IMAGE = 4
VIEW_TABLE = 5
VIEW_MERGE = 6
_BASE_VIEW_COUNT = 7

_BASE_VIEW_LABELS = {
    VIEW_HOME: "Home",
    VIEW_FOLDER: "Folder Compare",
    VIEW_TEXT: "Text Compare",
    VIEW_HEX: "Hex Compare",
    VIEW_IMAGE: "Image Compare",
    VIEW_TABLE: "Table Compare",
    VIEW_MERGE: "3-Way Merge",
}

# Views whose content is a folder tree; folder-only chrome is meaningful
# only here (WI-7.13's contextual-chrome rule, applied to the footer).
_FOLDER_CONTEXT_VIEWS = frozenset({VIEW_FOLDER})

# How many left/right pairs the Home view's "Recent sessions" list keeps.
_MAX_RECENT_SESSIONS = 10

_DIFF_OPTION_LABELS: dict[str, str] = {
    "show_all": "Show &All Items",
    "show_differences": "Show &Differences",
    "show_no_orphans": "Show &No Orphans",
    "show_differences_no_orphans": "Show Differences but No &Orphans",
    "show_orphans": "Show O&rphans",
    "show_left_newer": "Show &Left Newer",
    "show_right_newer": "Show &Right Newer",
    "show_left_newer_left_orphans": "Show Left Newer and Left Orphans",
    "show_right_newer_right_orphans": "Show Right Newer and Right Orphans",
    "show_left_orphans": "Show Left Orp&hans",
    "show_right_orphans": "Show Right Orpha&ns",
}
assert set(_DIFF_OPTION_LABELS) == set(DIFF_OPTION_MODES)


def _running_under_kde() -> bool:
    """Return whether the current session is a KDE Plasma desktop."""
    desktops = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return "kde" in desktops.lower() or bool(os.environ.get("KDE_FULL_SESSION"))


@dataclass
class SessionState:
    """Per-tab session state."""

    name: str
    left_path: str = ""
    right_path: str = ""
    base_path: str = ""
    settings: ComparisonSettings = field(default_factory=ComparisonSettings)
    three_way_mode: bool = False
    # One typed object rather than seven loose fields that could (and did)
    # drift apart from the controls displaying them.
    filters: FolderFilterState = field(default_factory=FolderFilterState)
    active_view: int = 0
    report: Optional[ScanReport] = None
    status_summary: str = "Ready"
    folder_view_mode: str = "compare_structure"
    always_show_folders: bool = True


class MainWindow(QMainWindow):
    """Central application window that wires together all views, menus,
    toolbar actions and background workers.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        log_info("initializing main window")

        # --- Core state ------------------------------------------------
        self._config: AppConfig = config
        self._app_state = AppState(config)
        self._worker: Optional[ComparisonWorker] = None
        self._copy_worker: Optional[CliJsonWorker] = None
        self._sync_worker: Optional[CliJsonWorker] = None
        self._current_report: Optional[ScanReport] = None
        self._diff_entries_cache: Optional[tuple] = None
        self._all_file_entries_cache: Optional[tuple] = None
        self._settings: ComparisonSettings = ComparisonSettings()
        profiles_path = (
            Path(config._config_file).with_name("profiles.json")
            if config._config_file
            else None
        )
        self._profile_manager: ProfileManager = ProfileManager(profiles_path)
        self._undo_history: OperationHistory = OperationHistory()
        self._three_way_mode: bool = False
        self._closing = False

        # The single source of truth for folder filtering. Every input surface
        # (View menu, status pills, search field, session restore) reads and
        # writes this object; _apply_filter_state() is the only publisher.
        self._filter_state: FolderFilterState = FolderFilterState.from_dict(
            config.filter_options
        )
        self._diff_options: dict = dict(config.diff_options)
        self._file_options: dict = dict(config.file_options)

        # Paths cached from the PathBar
        # Filter application is deferred and coalesced — see _on_filters_changed.
        self._pending_filters: FolderFilterState | None = None
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(120)
        self._filter_timer.timeout.connect(self._apply_pending_filters)

        self._left_path: str = ""
        self._right_path: str = ""
        self._base_path: str = ""
        self._sessions: list[SessionState] = []
        self._active_session_index: int = -1
        # tab key -> view-stack index for open comparison documents
        self._file_compare_tabs: dict[str, int] = {}
        self._nav_total: int = 0
        self._nav_index: int = 0
        # Persistent status summary; the visible footer owns the rendering.
        self._status_summary: str = "Ready"

        # --- CLI bridge ------------------------------------------------
        self._cli_bridge: Optional[CliBridge] = None
        try:
            cli_path = config.get_cli_path()
            self._cli_bridge = CliBridge(cli_path)
            log_info("cli bridge ready", cli_path=cli_path)
        except FileNotFoundError as exc:
            # Defer the dialog until after the window is shown so the
            # event loop is running.
            self._deferred_cli_error: Optional[str] = str(exc)
            log_warning("cli bridge unavailable", details=str(exc))
        else:
            self._deferred_cli_error = None

        # --- Window properties -----------------------------------------
        self.setWindowTitle("RCompare - File Comparison Tool")
        self.setMinimumSize(800, 600)
        self.setAcceptDrops(True)

        # --- Build UI --------------------------------------------------
        # No _build_toolbar(): the toolbar was removed in favour of the menu,
        # sidebar, and the session tab bar's Compare/Stop buttons.
        self._build_menu_bar()
        self._apply_saved_shortcuts()
        self._build_central_widget()
        self._build_status_bar()

        # --- Signal wiring ---------------------------------------------
        self._connect_signals()
        self._restore_persistent_state()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _themed_icon(self, *names: str, fallback: str | None = None) -> QIcon:
        """Resolve the first available theme icon, else an embedded fallback.

        Sessions without a complete FreeDesktop icon theme (minimal Wayland
        compositors, Windows, macOS) otherwise render blank menus and buttons.
        """
        return icons.first_available(*names, fallback_svg=fallback)

    def _build_menu_bar(self) -> None:
        menu_bar: QMenuBar = self.menuBar()

        # -- File -------------------------------------------------------
        file_menu = menu_bar.addMenu("&File")

        self._act_new_tab = QAction(self._themed_icon("tab-new"), "&New Tab", self)
        self._act_new_tab.setShortcut(QKeySequence.StandardKey.AddTab)  # Ctrl+T
        file_menu.addAction(self._act_new_tab)

        self._act_open_diff = QAction(self._themed_icon("document-open"), "&Open Diff...", self)
        self._act_open_diff.setShortcut(QKeySequence.StandardKey.Open)  # Ctrl+O
        file_menu.addAction(self._act_open_diff)

        self._act_compare_files = QAction(
            self._themed_icon("system-search"), "Compare &Files/Folders...", self
        )
        file_menu.addAction(self._act_compare_files)

        file_menu.addSeparator()

        self._act_save_diff = QAction(self._themed_icon("document-save"), "&Save Diff...", self)
        self._act_save_diff.setShortcut(QKeySequence.StandardKey.Save)  # Ctrl+S
        file_menu.addAction(self._act_save_diff)

        self._act_save_all = QAction(
            self._themed_icon("document-save-all"), "Save &All...", self
        )
        self._act_save_all.setShortcut(QKeySequence("Ctrl+Shift+S"))
        file_menu.addAction(self._act_save_all)

        file_menu.addSeparator()

        self._act_print = QAction(self._themed_icon("document-print"), "&Print...", self)
        self._act_print.setShortcut(QKeySequence.StandardKey.Print)  # Ctrl+P
        file_menu.addAction(self._act_print)

        self._act_print_preview = QAction(
            self._themed_icon("document-print-preview"), "Print Pre&view...", self
        )
        file_menu.addAction(self._act_print_preview)

        file_menu.addSeparator()

        self._act_close_tab = QAction(self._themed_icon("tab-close"), "&Close Tab", self)
        self._act_close_tab.setShortcut(QKeySequence.StandardKey.Close)  # Ctrl+W
        file_menu.addAction(self._act_close_tab)

        self._act_quit = QAction(self._themed_icon("application-exit"), "&Quit", self)
        # StandardKey.Quit resolves to the Exit *multimedia* key on Linux,
        # which no keyboard can produce. standard_key() falls back to Ctrl+Q.
        self._act_quit.setShortcut(
            standard_key(QKeySequence.StandardKey.Quit, "Ctrl+Q")
        )
        file_menu.addAction(self._act_quit)

        # -- Edit -------------------------------------------------------
        edit_menu = menu_bar.addMenu("&Edit")

        self._act_undo = QAction(self._themed_icon("edit-undo"), "&Undo Delete", self)
        self._act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._act_undo.setEnabled(False)
        edit_menu.addAction(self._act_undo)

        self._act_redo = QAction(self._themed_icon("edit-redo"), "&Redo Delete", self)
        self._act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._act_redo.setEnabled(False)
        edit_menu.addAction(self._act_redo)

        edit_menu.addSeparator()

        self._act_copy_lr = QAction(
            self._themed_icon("go-next"),
            "Copy &Left to Right",
            self,
        )
        self._act_copy_lr.setShortcut(QKeySequence(Qt.Key.Key_F7))
        edit_menu.addAction(self._act_copy_lr)

        self._act_copy_rl = QAction(
            self._themed_icon("go-previous"),
            "Copy &Right to Left",
            self,
        )
        self._act_copy_rl.setShortcut(QKeySequence(Qt.Key.Key_F8))
        edit_menu.addAction(self._act_copy_rl)

        edit_menu.addSeparator()

        self._act_swap_sides = QAction(
            self._themed_icon("view-sort-descending", "object-flip-horizontal"),
            "S&wap Sides",
            self,
        )
        # Removed Ctrl+W to avoid conflict with Close Tab
        edit_menu.addAction(self._act_swap_sides)

        edit_menu.addSeparator()

        self._act_find = QAction(
            self._themed_icon("edit-find"),
            "&Find...",
            self,
        )
        self._act_find.setShortcut(QKeySequence.StandardKey.Find)  # Ctrl+F
        edit_menu.addAction(self._act_find)

        self._act_find_next = QAction("Find &Next", self)
        self._act_find_next.setShortcut(QKeySequence.StandardKey.FindNext)  # F3
        edit_menu.addAction(self._act_find_next)

        self._act_find_prev = QAction("Find &Previous", self)
        self._act_find_prev.setShortcut(QKeySequence.StandardKey.FindPrevious)  # Shift+F3
        edit_menu.addAction(self._act_find_prev)

        # -- Difference -------------------------------------------------
        diff_menu = menu_bar.addMenu("&Difference")

        self._act_prev_file = QAction(
            self._themed_icon("go-up"),
            "&Previous File",
            self,
        )
        self._act_prev_file.setShortcut(QKeySequence("Ctrl+Up"))
        diff_menu.addAction(self._act_prev_file)

        self._act_next_file = QAction(
            self._themed_icon("go-down"),
            "&Next File",
            self,
        )
        self._act_next_file.setShortcut(QKeySequence("Ctrl+Down"))
        diff_menu.addAction(self._act_next_file)

        diff_menu.addSeparator()

        self._act_prev_diff = QAction(
            self._themed_icon("go-up-skip", "go-up"),
            "Previous &Difference",
            self,
        )
        self._act_prev_diff.setShortcut(QKeySequence("Alt+Up"))
        diff_menu.addAction(self._act_prev_diff)

        self._act_next_diff = QAction(
            self._themed_icon("go-down-skip", "go-down"),
            "Next D&ifference",
            self,
        )
        self._act_next_diff.setShortcut(QKeySequence("Alt+Down"))
        diff_menu.addAction(self._act_next_diff)

        diff_menu.addSeparator()

        self._act_apply_diff = QAction(
            self._themed_icon("dialog-ok-apply", "dialog-ok"),
            "&Apply Difference (L->R)",
            self,
        )
        self._act_apply_diff.setShortcut(QKeySequence("Ctrl+Return"))
        diff_menu.addAction(self._act_apply_diff)

        self._act_unapply_diff = QAction(
            self._themed_icon("edit-undo"),
            "&Unapply Difference (R->L)",
            self,
        )
        self._act_unapply_diff.setShortcut(QKeySequence("Ctrl+Backspace"))
        diff_menu.addAction(self._act_unapply_diff)

        diff_menu.addSeparator()

        self._act_apply_all = QAction(
            self._themed_icon("dialog-ok"),
            "Apply A&ll (L->R)",
            self,
        )
        diff_menu.addAction(self._act_apply_all)

        self._act_unapply_all = QAction(
            self._themed_icon("edit-undo"),
            "Unapply Al&l (R->L)",
            self,
        )
        diff_menu.addAction(self._act_unapply_all)

        diff_menu.addSeparator()

        self._act_diff_stats = QAction(
            self._themed_icon("view-statistics"),
            "&Statistics...",
            self,
        )
        diff_menu.addAction(self._act_diff_stats)

        # -- View -------------------------------------------------------
        view_menu = menu_bar.addMenu("&View")

        self._act_refresh = QAction(
            self._themed_icon("view-refresh"),
            "&Refresh",
            self,
        )
        self._act_refresh.setShortcut(QKeySequence.StandardKey.Refresh)  # F5
        view_menu.addAction(self._act_refresh)

        view_menu.addSeparator()

        compare_submenu = view_menu.addMenu("Compare &Mode")
        self._view_action_group = QActionGroup(self)
        self._view_action_group.setExclusive(True)

        self._act_view_folder = QAction("&Folder Compare", self)
        self._act_view_folder.setCheckable(True)
        self._act_view_folder.setChecked(True)
        self._view_action_group.addAction(self._act_view_folder)
        compare_submenu.addAction(self._act_view_folder)

        self._act_view_text = QAction("&Text Compare", self)
        self._act_view_text.setCheckable(True)
        self._view_action_group.addAction(self._act_view_text)
        compare_submenu.addAction(self._act_view_text)

        self._act_view_hex = QAction("&Hex Compare", self)
        self._act_view_hex.setCheckable(True)
        self._view_action_group.addAction(self._act_view_hex)
        compare_submenu.addAction(self._act_view_hex)

        self._act_view_image = QAction("&Image Compare", self)
        self._act_view_image.setCheckable(True)
        self._view_action_group.addAction(self._act_view_image)
        compare_submenu.addAction(self._act_view_image)

        self._act_view_table = QAction("&Table Compare", self)
        self._act_view_table.setCheckable(True)
        self._view_action_group.addAction(self._act_view_table)
        compare_submenu.addAction(self._act_view_table)

        # The sidebar has always advertised a 3-Way Merge destination; without
        # this entry the only way in was a switch that silently did nothing.
        self._act_view_merge = QAction("3-&Way Merge", self)
        self._act_view_merge.setCheckable(True)
        self._view_action_group.addAction(self._act_view_merge)
        compare_submenu.addAction(self._act_view_merge)

        view_menu.addSeparator()

        filter_submenu = view_menu.addMenu("&Filter")
        self._filter_action_group = QActionGroup(self)
        self._filter_action_group.setExclusive(True)

        self._act_filter_all = QAction("&All Items", self)
        self._act_filter_all.setCheckable(True)
        self._filter_action_group.addAction(self._act_filter_all)
        filter_submenu.addAction(self._act_filter_all)

        self._act_filter_diffs = QAction("&Differences Only", self)
        self._act_filter_diffs.setCheckable(True)
        self._filter_action_group.addAction(self._act_filter_diffs)
        filter_submenu.addAction(self._act_filter_diffs)

        self._act_filter_same = QAction("&Same Items Only", self)
        self._act_filter_same.setCheckable(True)
        self._filter_action_group.addAction(self._act_filter_same)
        filter_submenu.addAction(self._act_filter_same)

        view_menu.addSeparator()

        show_hide_submenu = view_menu.addMenu("Show/&Hide")

        self._act_show_identical = QAction("Show &Identical Files", self)
        self._act_show_identical.setCheckable(True)
        self._act_show_identical.setChecked(True)
        show_hide_submenu.addAction(self._act_show_identical)

        self._act_show_different = QAction("Show &Different Files", self)
        self._act_show_different.setCheckable(True)
        self._act_show_different.setChecked(True)
        show_hide_submenu.addAction(self._act_show_different)

        self._act_show_left_only = QAction("Show &Left Only", self)
        self._act_show_left_only.setCheckable(True)
        self._act_show_left_only.setChecked(True)
        show_hide_submenu.addAction(self._act_show_left_only)

        self._act_show_right_only = QAction("Show &Right Only", self)
        self._act_show_right_only.setCheckable(True)
        self._act_show_right_only.setChecked(True)
        show_hide_submenu.addAction(self._act_show_right_only)

        self._act_show_files_only = QAction("Show F&iles Only (No Folders)", self)
        self._act_show_files_only.setCheckable(True)
        self._act_show_files_only.setChecked(False)
        show_hide_submenu.addAction(self._act_show_files_only)

        # The diff-option modes used to live only on the hidden FilterBar, so
        # the proxy could sit in "show_differences" while every visible control
        # claimed identical rows were shown. They are menu entries now.
        diff_option_submenu = view_menu.addMenu("&Diff Options")
        self._diff_option_group = QActionGroup(self)
        self._diff_option_group.setExclusive(True)
        self._diff_option_actions: dict[str, QAction] = {}
        for mode, label in _DIFF_OPTION_LABELS.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(mode)
            self._diff_option_group.addAction(action)
            diff_option_submenu.addAction(action)
            self._diff_option_actions[mode] = action

        view_menu.addSeparator()

        folder_opts_menu = view_menu.addMenu("Folder &Options")
        self._act_always_show_folders = QAction("Always Show Folders", self)
        self._act_always_show_folders.setCheckable(True)
        self._act_always_show_folders.setChecked(True)
        folder_opts_menu.addAction(self._act_always_show_folders)

        self._folder_mode_group = QActionGroup(self)
        self._folder_mode_group.setExclusive(True)

        self._act_mode_compare_structure = QAction(
            "Compare Folder Structure",
            self,
        )
        self._act_mode_compare_structure.setCheckable(True)
        self._act_mode_compare_structure.setChecked(True)
        self._folder_mode_group.addAction(self._act_mode_compare_structure)
        folder_opts_menu.addAction(self._act_mode_compare_structure)

        self._act_mode_files_only = QAction("Only Compare Files", self)
        self._act_mode_files_only.setCheckable(True)
        self._folder_mode_group.addAction(self._act_mode_files_only)
        folder_opts_menu.addAction(self._act_mode_files_only)

        self._act_mode_ignore_structure = QAction("Ignore Folder Structure", self)
        self._act_mode_ignore_structure.setCheckable(True)
        self._folder_mode_group.addAction(self._act_mode_ignore_structure)
        folder_opts_menu.addAction(self._act_mode_ignore_structure)

        view_menu.addSeparator()

        self._act_show_preview = QAction("Show &Preview Panel", self)
        self._act_show_preview.setCheckable(True)
        self._act_show_preview.setChecked(False)
        view_menu.addAction(self._act_show_preview)

        view_menu.addSeparator()

        self._act_expand_all = QAction("&Expand All", self)
        view_menu.addAction(self._act_expand_all)

        self._act_collapse_all = QAction("&Collapse All", self)
        view_menu.addAction(self._act_collapse_all)

        # -- Tools ------------------------------------------------------
        tools_menu = menu_bar.addMenu("&Tools")

        self._act_compare_now = QAction(
            self._themed_icon("system-search"),
            "&Compare Now",
            self,
        )
        self._act_compare_now.setShortcut(QKeySequence("Shift+F5"))
        tools_menu.addAction(self._act_compare_now)

        self._act_sync = QAction(
            self._themed_icon("view-refresh"),
            "&Synchronize...",
            self,
        )
        # Ctrl+Y is one of StandardKey.Redo's bindings on Linux/Windows.
        self._act_sync.setShortcut(QKeySequence("Ctrl+Shift+Y"))
        tools_menu.addAction(self._act_sync)

        tools_menu.addSeparator()

        self._act_profiles = QAction(
            self._themed_icon("document-open"),
            "&Profiles...",
            self,
        )
        # Ctrl+P belongs to Print (StandardKey.Print).
        self._act_profiles.setShortcut(QKeySequence("Ctrl+Shift+P"))
        tools_menu.addAction(self._act_profiles)

        # -- Bookmarks --------------------------------------------------
        self._bookmarks_menu = menu_bar.addMenu("&Bookmarks")

        self._act_add_bookmark = QAction(
            self._themed_icon("bookmark-new"),
            "&Add Bookmark...",
            self,
        )
        self._act_add_bookmark.setShortcut(QKeySequence("Ctrl+D"))
        self._bookmarks_menu.addAction(self._act_add_bookmark)

        self._act_manage_bookmarks = QAction(
            self._themed_icon("bookmarks-organize"),
            "&Manage Bookmarks...",
            self,
        )
        self._bookmarks_menu.addAction(self._act_manage_bookmarks)

        self._bookmarks_menu.addSeparator()
        self._bookmarks_separator_index = len(self._bookmarks_menu.actions())

        # -- Settings ---------------------------------------------------
        settings_menu = menu_bar.addMenu("&Settings")

        self._act_configure_shortcuts = QAction("Configure &Shortcuts...", self)
        self._act_configure_shortcuts.setShortcut(
            QKeySequence("Ctrl+Shift+,")
        )
        settings_menu.addAction(self._act_configure_shortcuts)

        # "Configure Toolbars..." was removed along with the toolbar itself;
        # a menu entry whose only behaviour is an apology is worse than none.

        settings_menu.addSeparator()

        self._act_preferences = QAction(
            self._themed_icon("configure", fallback=icons.SETTINGS_SVG),
            "Configure &RCompare...",
            self,
        )
        # StandardKey.Preferences resolves to the Settings multimedia key on
        # Linux, so the chord is stated explicitly here.
        self._act_preferences.setShortcut(
            standard_key(QKeySequence.StandardKey.Preferences, "Ctrl+,")
        )
        settings_menu.addAction(self._act_preferences)

        # -- Help -------------------------------------------------------
        help_menu = menu_bar.addMenu("&Help")

        self._act_handbook = QAction(
            self._themed_icon("help-contents"),
            "RCompare &Handbook",
            self,
        )
        self._act_handbook.setShortcut(QKeySequence.StandardKey.HelpContents)  # F1
        help_menu.addAction(self._act_handbook)

        help_menu.addSeparator()

        self._act_report_bug = QAction("&Report Bug...", self)
        help_menu.addAction(self._act_report_bug)

        self._act_about = QAction(self._themed_icon("help-about"), "&About RCompare", self)
        help_menu.addAction(self._act_about)

        # Offering "About KDE" on GNOME, Windows or macOS misrepresents what
        # the user is running.
        self._act_about_kde = QAction("About &KDE", self)
        if _running_under_kde():
            help_menu.addAction(self._act_about_kde)

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _build_central_widget(self) -> None:
        central = QWidget(self)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Left: Sidebar activity bar ──
        self._sidebar = Sidebar(central)
        root_layout.addWidget(self._sidebar)

        # ── Right: Content area ──
        content = QWidget(central)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Session tab bar with Compare/Stop buttons
        self._session_tab_bar = SessionTabBar(content)
        content_layout.addWidget(self._session_tab_bar)

        # Compact path bar (single row)
        self._compact_path_bar = CompactPathBar(content)
        content_layout.addWidget(self._compact_path_bar)

        # Stacked widget holding the views
        self._view_stack = QStackedWidget(content)

        # Home view (index 0)
        self._home_view = HomeView(
            self._config, self._view_stack, profile_manager=self._profile_manager
        )
        self._view_stack.addWidget(self._home_view)    # index 0

        self._folder_view = FolderView(self._view_stack)
        self._view_stack.addWidget(self._folder_view)  # index 1

        self._text_view = TextView(self._view_stack)
        self._configure_text_view(self._text_view)
        self._view_stack.addWidget(self._text_view)    # index 2
        if self._config.appearance:
            self._text_view.apply_appearance(self._config.appearance)

        self._hex_view = HexView(self._view_stack)
        self._view_stack.addWidget(self._hex_view)      # index 3

        self._image_view = ImageView(self._view_stack)
        self._view_stack.addWidget(self._image_view)    # index 4

        # Table view (lazily imported, index 5)
        self._table_view: Optional[QWidget]
        try:
            from .views.table_view import TableView
            self._table_view = TableView(self._view_stack)
            self._view_stack.addWidget(self._table_view)  # index 5
        except ImportError:
            self._table_view = None
            self._view_stack.addWidget(self._unavailable_view("Table Compare"))

        # Merge view (index 6). The sidebar has always offered a 3-Way Merge
        # destination; creating it here is what makes that destination real
        # instead of a switch into an index the stack does not have.
        self._merge_view: Optional[QWidget]
        try:
            from .views.merge_view import MergeView
            self._merge_view = MergeView(self._view_stack)
            self._view_stack.addWidget(self._merge_view)  # index 6
        except ImportError:
            self._merge_view = None
            self._view_stack.addWidget(self._unavailable_view("3-Way Merge"))
            log_warning("merge_view module not available")

        # Visible document strip for comparisons opened from Folder Compare.
        # Hidden until the first document exists.
        self._document_tabs = DocumentTabBar(content)
        content_layout.addWidget(self._document_tabs)

        content_layout.addWidget(self._view_stack, 1)  # stretch factor 1

        # Integrated status bar at bottom of content area
        self._integrated_status = IntegratedStatusBar(content)
        content_layout.addWidget(self._integrated_status)

        root_layout.addWidget(content, 1)  # content stretches

        self.setCentralWidget(central)

        self._path_bar = self._compact_path_bar

        # Initialize first session
        self._sessions = [SessionState(name="Session 1")]
        self._session_tab_bar.add_session("Session 1")
        self._active_session_index = 0

    def _unavailable_view(self, label: str) -> QWidget:
        """Placeholder kept at a fixed stack index when a view fails to import.

        Keeping the index occupied means every other view's index stays
        correct, and the user gets an explanation instead of landing on
        whatever happened to shift into that slot.
        """
        placeholder = QWidget(self._view_stack)
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message = QLabel(
            f"<b>{label} is unavailable</b><br>"
            "An optional dependency for this view could not be imported."
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        layout.addWidget(message)
        return placeholder

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        # The native QMainWindow status bar is hidden; IntegratedStatusBar is
        # the only status surface. Nothing may write to statusBar() —
        # tests/test_visible_shell.py enforces that.
        self.statusBar().hide()

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # ── New modern widgets ──
        # Sidebar -> view switching
        self._sidebar.view_requested.connect(self._switch_view)
        self._sidebar.action_requested.connect(self._on_sidebar_action)

        # Session tab bar
        self._session_tab_bar.new_session_requested.connect(self._on_new_session)
        self._session_tab_bar.session_changed.connect(self._on_session_changed)
        self._session_tab_bar.session_close_requested.connect(self._on_close_tab)
        self._session_tab_bar.compare_requested.connect(self._on_compare)
        self._session_tab_bar.stop_requested.connect(self._on_cancel)

        # Compact path bar
        self._compact_path_bar.left_path_changed.connect(self._on_left_path_changed)
        self._compact_path_bar.right_path_changed.connect(self._on_right_path_changed)
        self._compact_path_bar.base_path_changed.connect(self._on_base_path_changed)
        self._compact_path_bar.swap_requested.connect(self._on_swap_sides)

        # Integrated status bar
        self._integrated_status.filters_changed.connect(self._on_integrated_filters)
        self._integrated_status.search_changed.connect(self._on_search_changed)
        self._integrated_status.navigate_prev.connect(self._on_prev_diff)
        self._integrated_status.navigate_next.connect(self._on_next_diff)

        # File menu
        self._act_new_tab.triggered.connect(self._on_new_session)
        self._act_open_diff.triggered.connect(self._on_open_diff)
        self._act_compare_files.triggered.connect(self._on_compare_files_dialog)
        self._act_save_diff.triggered.connect(self._on_save_diff)
        self._act_save_all.triggered.connect(self._on_save_all)
        self._act_print.triggered.connect(self._on_print)
        self._act_print_preview.triggered.connect(self._on_print_preview)
        self._act_close_tab.triggered.connect(self._on_close_tab)
        self._act_quit.triggered.connect(self.close)

        # Edit menu
        self._act_undo.triggered.connect(self._on_undo)
        self._act_redo.triggered.connect(self._on_redo)
        self._act_copy_lr.triggered.connect(self._on_copy_lr)
        self._act_copy_rl.triggered.connect(self._on_copy_rl)
        self._act_swap_sides.triggered.connect(self._on_swap_sides)
        self._act_find.triggered.connect(self._on_find)
        self._act_find_next.triggered.connect(self._on_find_next)
        self._act_find_prev.triggered.connect(self._on_find_prev)

        # Difference menu
        self._act_prev_file.triggered.connect(self._on_prev_file)
        self._act_next_file.triggered.connect(self._on_next_file)
        self._act_prev_diff.triggered.connect(self._on_prev_diff)
        self._act_next_diff.triggered.connect(self._on_next_diff)
        self._act_apply_diff.triggered.connect(self._on_apply_diff)
        self._act_unapply_diff.triggered.connect(self._on_unapply_diff)
        self._act_apply_all.triggered.connect(self._on_apply_all)
        self._act_unapply_all.triggered.connect(self._on_unapply_all)
        self._act_diff_stats.triggered.connect(self._on_diff_stats)

        # View menu
        self._act_refresh.triggered.connect(self._on_refresh)
        self._act_expand_all.triggered.connect(self._folder_view.expand_all)
        self._act_collapse_all.triggered.connect(self._folder_view.collapse_all)

        # Tools menu
        self._act_compare_now.triggered.connect(self._on_compare)
        self._act_sync.triggered.connect(self._on_sync)
        self._act_profiles.triggered.connect(self._on_profiles)

        # Bookmarks menu
        self._act_add_bookmark.triggered.connect(self._on_add_bookmark)
        self._act_manage_bookmarks.triggered.connect(self._on_manage_bookmarks)

        # Settings menu
        self._act_configure_shortcuts.triggered.connect(self._on_configure_shortcuts)
        self._act_preferences.triggered.connect(self._on_preferences)

        # Help menu
        self._act_handbook.triggered.connect(self._on_handbook)
        self._act_report_bug.triggered.connect(self._on_report_bug)
        self._act_about.triggered.connect(self._on_about)
        self._act_about_kde.triggered.connect(self._on_about_kde)

        # (Old toolbar removed — actions accessible via menu and sidebar)

        # HomeView signals
        self._home_view.session_type_selected.connect(self._on_home_session_type)
        self._home_view.recent_session_selected.connect(self._on_home_recent_session)
        # Home used to emit this into the void, so its Saved Profiles list was
        # decorative.
        self._home_view.profile_selected.connect(self._on_home_profile_selected)

        # FolderView file activated -> detect type and switch view
        self._folder_view.file_activated.connect(self._on_file_activated)
        self._folder_view.context_command.connect(self._on_folder_context_command)

        # Visible document strip for comparisons opened from Folder Compare
        self._document_tabs.document_selected.connect(self._switch_view)
        self._document_tabs.document_close_requested.connect(self._on_close_document)
        # Folder selection drives which copy/apply actions make sense.
        self._folder_view.selection_changed.connect(self._update_action_states)

        # View menu radio actions -> switch view
        self._act_view_folder.triggered.connect(lambda: self._switch_view(VIEW_FOLDER))
        self._act_view_text.triggered.connect(lambda: self._switch_view(VIEW_TEXT))
        self._act_view_hex.triggered.connect(lambda: self._switch_view(VIEW_HEX))
        self._act_view_image.triggered.connect(lambda: self._switch_view(VIEW_IMAGE))
        self._act_view_table.triggered.connect(lambda: self._switch_view(VIEW_TABLE))
        self._act_view_merge.triggered.connect(lambda: self._switch_view(VIEW_MERGE))

        # View menu filter checkboxes -> the one filter state
        self._act_show_identical.toggled.connect(self._on_view_filter_toggled)
        self._act_show_different.toggled.connect(self._on_view_filter_toggled)
        self._act_show_left_only.toggled.connect(self._on_view_filter_toggled)
        self._act_show_right_only.toggled.connect(self._on_view_filter_toggled)
        self._act_show_files_only.toggled.connect(self._on_view_filter_toggled)
        self._act_filter_all.triggered.connect(
            lambda: self._apply_quick_filter_preset(PRESET_ALL)
        )
        self._act_filter_diffs.triggered.connect(
            lambda: self._apply_quick_filter_preset(PRESET_DIFFS)
        )
        self._act_filter_same.triggered.connect(
            lambda: self._apply_quick_filter_preset(PRESET_SAME)
        )
        for mode, action in self._diff_option_actions.items():
            action.triggered.connect(
                lambda checked=False, m=mode: self._on_diff_option_changed(m)
            )
        self._act_show_preview.toggled.connect(self._on_preview_toggled)
        self._act_always_show_folders.toggled.connect(self._on_folder_view_options_changed)
        self._act_mode_compare_structure.triggered.connect(self._on_folder_view_options_changed)
        self._act_mode_files_only.triggered.connect(self._on_folder_view_options_changed)
        self._act_mode_ignore_structure.triggered.connect(self._on_folder_view_options_changed)

        # (3-Way toggle available via menu only)

    # ------------------------------------------------------------------
    # Show event -- deferred CLI error dialog
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._deferred_cli_error is not None:
            msg = self._deferred_cli_error
            self._deferred_cli_error = None
            # Name the location that actually exists. "Tools > Options" has
            # never been a menu in this application.
            QMessageBox.warning(
                self,
                "CLI Not Found",
                f"{msg}\n\nSet the path in Settings \u2192 Configure RCompare \u2192 CLI.",
            )

    # ------------------------------------------------------------------
    # Session tabs
    # ------------------------------------------------------------------

    def _current_session(self) -> SessionState:
        idx = self._active_session_index
        if idx < 0 or idx >= len(self._sessions):
            idx = 0
        return self._sessions[idx]

    def _session_title(self, session: SessionState, index: int) -> str:
        left = Path(session.left_path).name if session.left_path else ""
        right = Path(session.right_path).name if session.right_path else ""
        if left and right:
            return f"{left} <> {right}"
        if left:
            return left
        if right:
            return right
        return f"Session {index + 1}"

    def _update_active_session_title(self) -> None:
        idx = self._active_session_index
        if idx < 0 or idx >= len(self._sessions):
            return
        session = self._sessions[idx]
        title = self._session_title(session, idx)
        session.name = title
        self._session_tab_bar.set_session_name(idx, title)

    def _capture_session_state(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._sessions):
            return
        session = self._sessions[idx]
        session.left_path = self._left_path
        session.right_path = self._right_path
        session.base_path = self._base_path
        session.settings = self._settings.copy()
        session.three_way_mode = self._three_way_mode
        # Captured from the live filter state, not from a hidden widget that
        # last saw a value several interactions ago.
        session.filters = self._filter_state
        session.active_view = self._view_stack.currentIndex()
        session.report = self._current_report
        session.status_summary = self._status_summary or "Ready"
        session.folder_view_mode = self._folder_view_mode()
        session.always_show_folders = self._act_always_show_folders.isChecked()
        self._update_active_session_title()

    def _apply_session_state(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._sessions):
            return

        session = self._sessions[idx]
        self._active_session_index = idx
        self._settings = session.settings.copy()

        self._path_bar.left_path = session.left_path
        self._path_bar.right_path = session.right_path
        self._path_bar.base_path = session.base_path
        self._left_path = session.left_path
        self._right_path = session.right_path
        self._base_path = session.base_path

        self._three_way_mode = session.three_way_mode
        self._path_bar.set_three_way_mode(session.three_way_mode)

        self._apply_filter_state(session.filters, persist_to_session=False)

        active = session.active_view
        if active < 0 or active >= self._view_stack.count():
            active = VIEW_FOLDER
        self._switch_view(active)

        self._current_report = session.report
        self._set_folder_view_options(session.folder_view_mode, session.always_show_folders)
        if session.report is not None:
            self._rebuild_folder_tree_from_report()
        else:
            self._folder_view.set_tree(
                TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
            )

        self._set_status_summary(session.status_summary or "Ready")
        self._session_tab_bar.set_comparing(False)
        self._refresh_navigation_counter()
        self._update_action_states()
        self._update_active_session_title()

    @Slot(int)
    def _on_session_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._sessions):
            return
        if self._worker is not None and self._worker.is_running():
            self._worker.cancel()
        old_index = self._active_session_index
        if old_index != index:
            self._capture_session_state(old_index)
        self._apply_session_state(index)

    # ------------------------------------------------------------------
    # Visible-shell feedback (WI-5.7)
    #
    # The native status bar is hidden, so these are the only ways to reach
    # the user with an operation message, progress or a diff position.
    # ------------------------------------------------------------------

    def _notify(self, text: str, timeout_ms: int = 0) -> None:
        """Show a transient operation message in the visible status bar."""
        self._integrated_status.show_message(text, timeout_ms)

    def _set_status_summary(self, text: str) -> None:
        """Set the persistent status summary shown when no message is active."""
        self._status_summary = text
        self._integrated_status.set_status(text)
        self._current_session().status_summary = text

    def _set_progress(self, percent: int, stage_label: str = "") -> None:
        """Publish structured progress to the visible bar.

        A negative *percent* means "working, total unknown" and shows Qt's
        indeterminate (busy) bar — used during the directory walk, whose total
        cannot be known until it completes.
        """
        if percent < 0:
            self._integrated_status.set_progress(0, 0)
        else:
            self._integrated_status.set_progress(percent, 100)
        self._integrated_status.set_stage(stage_label)

    def _end_progress(self) -> None:
        self._integrated_status.show_progress(False)

    def _set_navigation_position(self, index: int, total: int) -> None:
        """Publish the current difference position (the footer's ``n/m``)."""
        self._nav_index = index
        self._nav_total = total
        self._integrated_status.set_navigation_position(index, total)

    def _refresh_navigation_counter(self) -> None:
        """Recompute the footer counter after the report or view changes."""
        total = len(self._get_diff_entries())
        index = self._nav_index if self._nav_index <= total else 0
        self._set_navigation_position(index, total)

    # ------------------------------------------------------------------
    # Path slots
    # ------------------------------------------------------------------

    def _set_left_path(self, path: str) -> None:
        """Set the left path from code and keep every observer in step."""
        self._path_bar.blockSignals(True)
        self._path_bar.left_path = path
        self._path_bar.blockSignals(False)
        self._on_left_path_changed(path)

    def _set_right_path(self, path: str) -> None:
        """Set the right path from code and keep every observer in step."""
        self._path_bar.blockSignals(True)
        self._path_bar.right_path = path
        self._path_bar.blockSignals(False)
        self._on_right_path_changed(path)

    @Slot(str)
    def _on_left_path_changed(self, path: str) -> None:
        self._left_path = path
        self._app_state.left_path = path
        session = self._current_session()
        session.left_path = path
        self._update_active_session_title()

    @Slot(str)
    def _on_right_path_changed(self, path: str) -> None:
        self._right_path = path
        self._app_state.right_path = path
        session = self._current_session()
        session.right_path = path
        self._update_active_session_title()

    @Slot(str)
    def _on_base_path_changed(self, path: str) -> None:
        self._app_state.base_path = path
        self._base_path = path
        session = self._current_session()
        session.base_path = path

    # ------------------------------------------------------------------
    # Filtering (WI-5.9)
    #
    # _apply_filter_state() is the only writer. Every input surface converts
    # its event into a new FolderFilterState and hands it here, so the proxy,
    # the View menu, the footer pills and the session snapshot cannot disagree
    # about what is actually being shown.
    # ------------------------------------------------------------------

    @property
    def filter_state(self) -> FolderFilterState:
        """The applied folder-filter state (read by tests and session capture)."""
        return self._filter_state

    def _apply_filter_state(
        self, state: FolderFilterState, *, persist_to_session: bool = True
    ) -> None:
        """Adopt *state* as the truth and push it to every surface."""
        self._filter_state = state

        # Applying filters walks the whole tree (measured at ~700ms for 8k
        # entries) and scales with the result set, so it must not run inline on
        # a pill click. Coalesce rapid toggles into one deferred pass; the
        # control sync below still runs immediately so the click is reflected
        # at once.
        self._pending_filters = state
        self._filter_timer.start()

        self._sync_filter_controls(state)

        if persist_to_session:
            self._current_session().filters = state

    def _apply_pending_filters(self) -> None:
        """Run the coalesced proxy pass queued by _apply_filter_state()."""
        if self._pending_filters is None:
            return
        state, self._pending_filters = self._pending_filters, None
        self._folder_view.set_filters(
            state.show_identical,
            state.show_different,
            state.show_left_only,
            state.show_right_only,
            state.show_files_only,
            state.search_text,
            state.diff_option_mode,
        )

    def flush_pending_filters(self) -> None:
        """Apply any queued filter pass immediately (used by tests)."""
        self._filter_timer.stop()
        self._apply_pending_filters()

    def _sync_filter_controls(self, state: FolderFilterState) -> None:
        """Push *state* onto every control that displays it, without echoes."""
        for action, value in (
            (self._act_show_identical, state.show_identical),
            (self._act_show_different, state.show_different),
            (self._act_show_left_only, state.show_left_only),
            (self._act_show_right_only, state.show_right_only),
            (self._act_show_files_only, state.show_files_only),
        ):
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)

        preset = state.preset
        for action, name in (
            (self._act_filter_all, PRESET_ALL),
            (self._act_filter_diffs, PRESET_DIFFS),
            (self._act_filter_same, PRESET_SAME),
        ):
            action.blockSignals(True)
            action.setChecked(preset == name)
            action.blockSignals(False)

        for mode, action in self._diff_option_actions.items():
            action.blockSignals(True)
            action.setChecked(mode == state.diff_option_mode)
            action.blockSignals(False)

        self._integrated_status.set_filter_state(
            state.show_identical,
            state.show_different,
            state.show_left_only,
            state.show_right_only,
        )
        self._integrated_status.set_search_text(state.search_text)

    @Slot(str)
    def _on_diff_option_changed(self, mode: str) -> None:
        self._apply_filter_state(self._filter_state.with_diff_option_mode(mode))

    @Slot()
    def _on_view_filter_toggled(self) -> None:
        """Read the View menu checkboxes back into the filter state.

        These used to write into a hidden FilterBar whose signals were never
        connected, so toggling them changed nothing the user could see.
        """
        state = self._filter_state.with_statuses(
            self._act_show_identical.isChecked(),
            self._act_show_different.isChecked(),
            self._act_show_left_only.isChecked(),
            self._act_show_right_only.isChecked(),
        ).with_files_only(self._act_show_files_only.isChecked())
        self._apply_filter_state(state)

    def _apply_quick_filter_preset(self, preset: str) -> None:
        self._apply_filter_state(self._filter_state.with_preset(preset))

    def _folder_view_mode(self) -> str:
        if self._act_mode_files_only.isChecked():
            return "files_only"
        if self._act_mode_ignore_structure.isChecked():
            return "ignore_structure"
        return "compare_structure"

    @Slot()
    def _on_folder_view_options_changed(self) -> None:
        session = self._current_session()
        session.folder_view_mode = self._folder_view_mode()
        session.always_show_folders = self._act_always_show_folders.isChecked()
        self._rebuild_folder_tree_from_report()

    def _set_folder_view_options(self, mode: str, always_show_folders: bool) -> None:
        normalized = (mode or "compare_structure").strip().lower()
        if normalized not in {"compare_structure", "files_only", "ignore_structure"}:
            normalized = "compare_structure"

        self._act_always_show_folders.blockSignals(True)
        self._act_mode_compare_structure.blockSignals(True)
        self._act_mode_files_only.blockSignals(True)
        self._act_mode_ignore_structure.blockSignals(True)
        self._act_always_show_folders.setChecked(bool(always_show_folders))
        self._act_mode_compare_structure.setChecked(normalized == "compare_structure")
        self._act_mode_files_only.setChecked(normalized == "files_only")
        self._act_mode_ignore_structure.setChecked(normalized == "ignore_structure")
        self._act_always_show_folders.blockSignals(False)
        self._act_mode_compare_structure.blockSignals(False)
        self._act_mode_files_only.blockSignals(False)
        self._act_mode_ignore_structure.blockSignals(False)

    def _rebuild_folder_tree_from_report(self) -> None:
        report = self._current_report
        if report is None:
            return
        root: TreeNode = build_tree_with_options(
            report,
            self._folder_view_mode(),
            always_show_folders=self._act_always_show_folders.isChecked(),
        )
        self._folder_view.set_tree(root)

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @Slot()
    def _on_compare(self) -> None:
        """Validate paths and launch an asynchronous comparison."""
        left = self._path_bar.left_path.strip()
        right = self._path_bar.right_path.strip()
        log_info("compare requested", left=left, right=right)

        if not left or not right:
            log_warning("compare rejected: missing paths", left=left, right=right)
            QMessageBox.warning(
                self, "Missing Paths", "Please specify both left and right paths."
            )
            return

        left_path = Path(left)
        right_path = Path(right)

        if not left_path.exists():
            log_warning("compare rejected: left path missing", left=left)
            QMessageBox.critical(
                self, "Path Not Found", f"Left path does not exist:\n{left}"
            )
            return
        if not right_path.exists():
            log_warning("compare rejected: right path missing", right=right)
            QMessageBox.critical(
                self, "Path Not Found", f"Right path does not exist:\n{right}"
            )
            return

        if self._cli_bridge is None:
            log_error("compare rejected: cli bridge not configured")
            QMessageBox.critical(
                self,
                "CLI Not Found",
                "rcompare_cli binary is not configured. Please set the path in Tools > Options.",
            )
            return

        # Cancel any running worker
        if self._worker is not None and self._worker.is_running():
            self._worker.cancel()

        # Results from the previous run are stale the moment a new scan starts;
        # clearing here also lets partial snapshots through (they are ignored
        # while a completed report is present).
        self._current_report = None
        self._worker = ComparisonWorker(self._cli_bridge, self)
        self._worker.finished.connect(self._on_comparison_finished)
        self._worker.error.connect(self._on_comparison_error)
        self._worker.progress.connect(self._on_comparison_progress)
        self._worker.progress_update.connect(self._on_progress_update)
        self._worker.partial_ready.connect(self._on_partial_result)

        self._app_state.set_comparing(True)
        self._session_tab_bar.set_comparing(True)
        self._set_status_summary("Comparing...")
        self._set_progress(0, "Starting comparison...")
        self._update_action_states()

        self._worker.start_scan(
            left=left,
            right=right,
            follow_symlinks=self._settings.follow_symlinks,
            verify_hashes=self._settings.use_hash_verification,
            ignore_patterns=self._settings.ignore_patterns or None,
            cache_dir=self._settings.cache_dir,
            folder_view_mode=self._folder_view_mode(),
            always_show_folders=self._act_always_show_folders.isChecked(),
            **self._scan_options(),
        )
        log_info(
            "compare started",
            follow_symlinks=self._settings.follow_symlinks,
            verify_hashes=self._settings.use_hash_verification,
            ignore_count=len(self._settings.ignore_patterns or []),
        )

    @Slot()
    def _on_cancel(self) -> None:
        """Cancel a running comparison."""
        if self._worker is not None:
            self._worker.cancel()
        self._app_state.request_stop()
        self._app_state.set_comparing(False)
        self._session_tab_bar.set_comparing(False)
        self._end_progress()
        self._set_status_summary("Cancelled")
        self._update_action_states()

    @Slot(object)
    def _on_partial_result(self, partial) -> None:
        """Render a snapshot of a comparison that is still running.

        Keeps the folder view filling while the CLI streams results, instead of
        leaving it empty until the scan completes.
        """
        if self._closing or self._current_report is not None:
            # A newer comparison already completed; ignore stale snapshots.
            return
        self._folder_view.set_tree(partial.tree)
        self._folder_view.set_preview_roots(self._left_path, self._right_path)
        if self._view_stack.currentIndex() == 0:
            self._switch_view(1)
        summary = partial.summary
        if summary is not None:
            text = (
                f"Scanning... {partial.entries_seen:,} of {summary.total:,} entries"
            )
        else:
            text = f"Scanning... {partial.entries_seen:,} entries"
        self._set_status_summary(text)

    @Slot(object)
    def _on_comparison_finished(self, result: ComparisonResult | ScanReport) -> None:
        """Handle a completed comparison."""
        if self._closing:
            return
        if isinstance(result, ComparisonResult):
            report = result.report
            tree = result.tree
        else:
            # Direct report delivery remains supported for tests and plugins.
            report = result
            tree = build_tree_with_options(
                report,
                self._folder_view_mode(),
                always_show_folders=self._act_always_show_folders.isChecked(),
            )
        self._current_report = report
        self._app_state.set_results("scan_report", report)
        self._app_state.set_comparing(False)
        session = self._current_session()
        session.report = report
        self._session_tab_bar.set_comparing(False)
        self._end_progress()

        self._folder_view.set_tree(tree)
        self._folder_view.set_preview_roots(self._left_path, self._right_path)

        # Switch to folder view if we're on the home view
        if self._view_stack.currentIndex() == 0:
            self._switch_view(1)

        summary = report.summary
        status_text = (
            f"{summary.same} identical, "
            f"{summary.different} different, "
            f"{summary.orphan_left} left only, "
            f"{summary.orphan_right} right only"
        )
        # The status bar was set to "Comparing..." when the scan started;
        # without this it stays there for the rest of the session.
        self._set_status_summary(status_text)
        self._record_recent_session()
        self._update_action_states()

        # Update navigation counters
        diff_entries = self._get_diff_entries()
        all_entries = self._get_all_file_entries()
        self._set_navigation_position(0, len(diff_entries))
        self._notify(
            f"Comparison complete: {len(all_entries)} files, "
            f"{len(diff_entries)} differences.",
            6000,
        )
        log_info(
            "compare completed",
            total=report.summary.total,
            same=report.summary.same,
            different=report.summary.different,
            orphan_left=report.summary.orphan_left,
            orphan_right=report.summary.orphan_right,
            unchecked=report.summary.unchecked,
        )

    @Slot(str)
    def _on_comparison_error(self, message: str) -> None:
        """Handle a comparison error."""
        if self._closing:
            return
        self._app_state.set_comparing(False)
        self._app_state.error_occurred.emit(message)
        self._session_tab_bar.set_comparing(False)
        self._end_progress()
        self._set_status_summary("Error")
        self._update_action_states()
        log_error("compare failed", error_text=message)
        QMessageBox.critical(self, "Comparison Error", message)

    @Slot(str)
    def _on_comparison_progress(self, message: str) -> None:
        """Show progress messages in the status bar."""
        if self._closing:
            return
        self._notify(message)

    @Slot(object)
    def _on_progress_update(self, info) -> None:
        """Handle structured progress updates from the CLI."""
        self._app_state.update_progress(info)
        # Structured progress now drives the *visible* bar. It used to write
        # to a detached QProgressBar/QLabel pair, so the footer sat at 0%.
        if info.entries_total > 0:
            label = f"{info.stage_label} ({info.entries_done:,}/{info.entries_total:,})"
            self._set_progress(info.percent, label)
        elif info.entries_done > 0:
            # Directory walk: the total is unknowable until it finishes, so
            # report the running count instead of pinning the bar at 0%.
            label = f"{info.stage_label} ({info.entries_done:,} entries)"
            self._set_progress(-1, label)
        else:
            label = info.stage_label
            self._set_progress(info.percent, label)
        self._notify(label)

    # ------------------------------------------------------------------
    # Refresh / New Session
    # ------------------------------------------------------------------

    @Slot()
    def _on_refresh(self) -> None:
        """Re-run the comparison with the current paths."""
        if self._path_bar.left_path.strip() and self._path_bar.right_path.strip():
            self._on_compare()

    @Slot()
    def _on_home(self) -> None:
        """Show the Home/Welcome view."""
        self._switch_view(0)

    @Slot(str)
    def _on_sidebar_action(self, action_id: str) -> None:
        """Handle sidebar bottom action clicks."""
        if action_id == "bookmarks":
            self._on_manage_bookmarks()
        elif action_id == "settings":
            self._on_preferences()

    @Slot(bool, bool, bool, bool)
    def _on_integrated_filters(self, identical: bool, different: bool, left_only: bool, right_only: bool) -> None:
        """Handle status-pill changes from IntegratedStatusBar."""
        self._apply_filter_state(
            replace(
                self._filter_state,
                show_identical=identical,
                show_different=different,
                show_left_only=left_only,
                show_right_only=right_only,
            )
        )

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        """Handle search text changes from IntegratedStatusBar."""
        self._apply_filter_state(replace(self._filter_state, search_text=text))

    def _record_recent_session(self) -> None:
        """Remember the current pair in config.recent_sessions (most recent first)."""
        left, right = self._left_path, self._right_path
        if not left or not right:
            return
        entries = [
            e for e in self._config.recent_sessions
            if not (e.get("left") == left and e.get("right") == right)
        ]
        entries.insert(0, {"left": left, "right": right})
        del entries[_MAX_RECENT_SESSIONS:]
        self._config.recent_sessions = entries
        # Home renders this list; refresh it now rather than only at startup.
        self._home_view.refresh(self._config, self._profile_manager)

    def _update_action_states(self) -> None:
        """Enable or disable actions according to what the session can do now.

        Presenting every action in every context makes the menu unreliable:
        the user cannot tell which commands apply. Each group below is gated on
        the precondition its handler would otherwise fail on, and a disabled
        action carries a tooltip saying what is missing.
        """
        has_report = self._current_report is not None
        comparing = self._worker is not None and self._worker.is_running()
        has_paths = bool(self._left_path.strip() and self._right_path.strip())
        has_cli = self._cli_bridge is not None
        view = self._view_stack.currentIndex()
        is_folder = view in _FOLDER_CONTEXT_VIEWS
        has_selection = bool(self._folder_view.selected_paths()) if is_folder else False

        # -- Compare: needs both paths and a working CLI --------------------
        can_compare = has_paths and has_cli and not comparing
        if comparing:
            reason = "A comparison is already running."
        elif not has_paths:
            reason = "Set both a left and a right path first."
        elif not has_cli:
            reason = "rcompare_cli is not configured (Settings \u2192 CLI)."
        else:
            reason = ""
        for action in (self._act_refresh, self._act_compare_now):
            action.setEnabled(can_compare)
            action.setToolTip(reason)
        self._session_tab_bar.set_compare_enabled(can_compare, reason)

        # -- Results-dependent commands -------------------------------------
        for action in (
            self._act_next_diff,
            self._act_prev_diff,
            self._act_next_file,
            self._act_prev_file,
            self._act_diff_stats,
            self._act_sync,
            self._act_save_diff,
            self._act_print,
            self._act_print_preview,
        ):
            action.setEnabled(has_report)
            action.setToolTip("" if has_report else "Run a comparison first.")

        # -- Folder-tree-only commands ---------------------------------------
        for action in (self._act_expand_all, self._act_collapse_all):
            action.setEnabled(is_folder and has_report)
            action.setToolTip("" if is_folder else "Available in Folder Compare.")

        # -- Selection-driven copy/apply -------------------------------------
        for action in (
            self._act_copy_lr,
            self._act_copy_rl,
            self._act_apply_diff,
            self._act_unapply_diff,
        ):
            action.setEnabled(has_selection)
            action.setToolTip(
                "" if has_selection else "Select an item in Folder Compare first."
            )
        bulk_ok = has_report and is_folder
        for action in (self._act_apply_all, self._act_unapply_all, self._act_save_all):
            action.setEnabled(bulk_ok)
            action.setToolTip("" if bulk_ok else "Run a folder comparison first.")

        # -- Paths ------------------------------------------------------------
        self._act_swap_sides.setEnabled(has_paths and not comparing)
        self._act_add_bookmark.setEnabled(has_paths)
        self._act_close_tab.setEnabled(len(self._sessions) > 1)

    @Slot(int)
    def _on_home_session_type(self, view_index: int) -> None:
        """Open the comparison type chosen on a Home card.

        HomeView emits the *stack* index directly, so adding a card can never
        silently land on a different view again.
        """
        self._switch_view(view_index)

    @Slot(str, str)
    def _on_home_recent_session(self, left: str, right: str) -> None:
        """Open a recent pair from Home and start comparing it."""
        self._path_bar.left_path = left
        self._path_bar.right_path = right
        self._on_left_path_changed(left)
        self._on_right_path_changed(right)
        self._switch_view(VIEW_FOLDER)
        self._on_compare()

    @Slot(str)
    def _on_home_profile_selected(self, profile_id: str) -> None:
        """Open a saved profile chosen on Home.

        Home used to emit this signal into nothing, and read its profile list
        from ``comparison_settings["profiles"]`` -- a key ProfileManager never
        writes. Both sides now go through ProfileManager.
        """
        profile = self._profile_manager.get(profile_id)
        if profile is None:
            self._notify(f"Profile '{profile_id}' is no longer available.", 6000)
            log_warning("home profile activation failed", profile_id=profile_id)
            return
        self._apply_profile(profile)
        self._switch_view(VIEW_FOLDER)
        if profile.left_path and profile.right_path:
            self._on_compare()

    @Slot()
    def _on_swap_sides(self) -> None:
        """Swap the compared sides. Sole owner of the mutation.

        The path widget used to swap its own breadcrumbs *and* emit
        ``swap_requested``, so this handler swapped a second time and the
        visible result was no change at all. The widget now only signals
        intent; session and window state are updated from here.
        """
        left, right = self._left_path, self._right_path
        self._left_path, self._right_path = right, left

        # Push to the widget with signals blocked: it is a view of this state,
        # not a second copy of it.
        self._path_bar.blockSignals(True)
        self._path_bar.left_path = right
        self._path_bar.right_path = left
        self._path_bar.blockSignals(False)

        self._app_state.left_path = right
        self._app_state.right_path = left
        session = self._current_session()
        session.left_path = right
        session.right_path = left

        # The report describes the old orientation; keeping it would label
        # left-only rows as right-only.
        self._current_report = None
        session.report = None
        self._folder_view.set_tree(
            TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
        )
        self._refresh_navigation_counter()
        self._update_active_session_title()
        self._update_action_states()
        self._notify("Swapped left and right. Compare again to refresh.", 6000)

    @Slot()
    def _on_focus_filter_search(self) -> None:
        self._integrated_status.focus_search()

    @Slot()
    def _on_clear_filter_search(self) -> None:
        self._integrated_status.clear_search()

    @Slot()
    def _on_new_session(self) -> None:
        """Create a new comparison session tab."""
        # Cancel any running comparison
        if self._worker is not None and self._worker.is_running():
            self._worker.cancel()
        self._capture_session_state(self._active_session_index)

        new_index = len(self._sessions)
        session = SessionState(name=f"Session {new_index + 1}")
        self._sessions.append(session)
        # add_session() selects the new tab, which drives _on_session_changed
        # and therefore _apply_session_state.
        self._session_tab_bar.add_session(session.name)
        self._notify(f"Opened {session.name}.", 4000)

    @Slot(int)
    def _close_session(self, index: int) -> None:
        """Close the session at visible tab *index*.

        The old implementation compared this index against the number of
        *view* tabs (6) and subtracted that offset before deleting, so the
        first six sessions could not be closed and any close that did happen
        removed the wrong entry.
        """
        if index < 0 or index >= len(self._sessions):
            return
        if len(self._sessions) <= 1:
            self._notify("The last session cannot be closed.", 4000)
            return

        if (
            index == self._active_session_index
            and self._worker is not None
            and self._worker.is_running()
        ):
            self._worker.cancel()

        name = self._sessions[index].name
        del self._sessions[index]

        if self._active_session_index > index:
            self._active_session_index -= 1
        elif self._active_session_index == index:
            self._active_session_index = min(index, len(self._sessions) - 1)

        # Removing the tab re-emits currentChanged; _on_session_changed reads
        # _active_session_index, which is already correct above.
        self._session_tab_bar.remove_session(index)
        self._session_tab_bar.current_index = self._active_session_index
        self._apply_session_state(self._active_session_index)
        self._notify(f"Closed {name}.", 4000)
        log_info("session closed", index=index, remaining=len(self._sessions))

    @property
    def session_count(self) -> int:
        """Number of open sessions (used by tests)."""
        return len(self._sessions)

    # ------------------------------------------------------------------
    # View switching and open documents (WI-5.8)
    # ------------------------------------------------------------------

    _VIEW_ACTIONS_ATTR = (
        (VIEW_FOLDER, "_act_view_folder"),
        (VIEW_TEXT, "_act_view_text"),
        (VIEW_HEX, "_act_view_hex"),
        (VIEW_IMAGE, "_act_view_image"),
        (VIEW_TABLE, "_act_view_table"),
        (VIEW_MERGE, "_act_view_merge"),
    )

    @Slot(int)
    def _switch_view(self, index: int) -> None:
        """Make *index* the active view and bring every indicator along.

        Accepts both base-view indices and document indices; the sidebar,
        Compare Mode radio group, document strip and contextual chrome are all
        derived from it, so there is no second place a view can be "current".
        """
        if index < 0 or index >= self._view_stack.count():
            log_warning("view switch rejected: no such view", index=index)
            return
        self._view_stack.setCurrentIndex(index)

        base_views = (
            ActiveView.HOME,
            ActiveView.FOLDER,
            ActiveView.TEXT,
            ActiveView.HEX,
            ActiveView.IMAGE,
            ActiveView.TABLE,
            ActiveView.MERGE,
        )
        if index < len(base_views):
            self._app_state.set_active_view(base_views[index])
            self._sidebar.set_active_view(index)
            # Documents belong to the base view they were opened from; leaving
            # for a different base view resets the strip's context.
            self._document_tabs.set_context(
                _BASE_VIEW_LABELS.get(index, "Comparison"), index
            )

        for view_index, attr in self._VIEW_ACTIONS_ATTR:
            action = getattr(self, attr)
            action.blockSignals(True)
            action.setChecked(view_index == index)
            action.blockSignals(False)

        self._document_tabs.select_stack_index(index)
        self._current_session().active_view = index
        self._apply_contextual_chrome(index)
        self._update_action_states()

    def _apply_contextual_chrome(self, index: int) -> None:
        """Show folder-only chrome only where a folder tree is on screen.

        Folder paths and status filters used to stay visible on Home, Text,
        Hex, Image, Table and Merge, where they control nothing.
        """
        is_folder = index in _FOLDER_CONTEXT_VIEWS
        self._integrated_status.set_filters_enabled(is_folder)
        # Home has no paths to compare; every other view does.
        self._compact_path_bar.setVisible(index != VIEW_HOME)

    @property
    def active_view_index(self) -> int:
        """Stack index of the visible view (used by tests)."""
        return self._view_stack.currentIndex()

    @property
    def open_document_count(self) -> int:
        """Number of dynamically opened comparison documents."""
        return self._document_tabs.document_count

    @Slot(int)
    def _on_close_document(self, index: int) -> None:
        """Close the comparison document living at stack *index*.

        Base views are permanent; only indices at or beyond _BASE_VIEW_COUNT
        represent closable documents.
        """
        if index < _BASE_VIEW_COUNT or index >= self._view_stack.count():
            return

        widget = self._view_stack.widget(index)
        if widget is None:
            return

        maybe_close = getattr(widget, "maybe_close", None)
        if callable(maybe_close) and not maybe_close():
            return

        # Give a view with background work a chance to stop it before teardown.
        cancel = getattr(widget, "cancel_pending", None)
        if callable(cancel):
            cancel()

        self._view_stack.removeWidget(widget)
        widget.deleteLater()

        # Every stack index above the removed one shifts down by one.
        remap = {
            old: old - 1
            for old in range(index + 1, index + 1 + self._view_stack.count() - index)
        }
        self._document_tabs.remove_document(index)
        self._document_tabs.reindex(remap)
        self._file_compare_tabs = {
            key: remap.get(stack_index, stack_index)
            for key, stack_index in self._file_compare_tabs.items()
            if stack_index != index
        }

        remaining = self._document_tabs.stack_indices()
        next_index = remaining[-1] if len(remaining) > 1 else VIEW_FOLDER
        self._switch_view(next_index)
        self._notify("Comparison closed.", 4000)
        log_info("comparison document closed", index=index)

    # ------------------------------------------------------------------
    # File activation (double-click in FolderView)
    # ------------------------------------------------------------------

    @Slot(str, bool)
    def _on_file_activated(self, path: str, is_dir: bool) -> None:
        """Open or activate a file-compare tab when the user double-clicks a file."""
        if is_dir:
            return

        resolved = self._resolve_compare_file_paths(path)
        if resolved is None:
            log_warning("file activation rejected", rel_path=path)
            QMessageBox.information(
                self,
                "File Compare Not Available",
                "Selected item is not available as a file on both sides.",
            )
            return

        left_file, right_file = resolved
        mode = self._determine_file_compare_mode(path)
        tab_key = self._make_file_tab_key(mode, left_file, right_file)

        existing = self._file_compare_tabs.get(tab_key)
        if existing is not None and 0 <= existing < self._view_stack.count():
            self._switch_view(existing)
            log_info("file compare tab reused", rel_path=path, mode=mode, index=existing)
            return

        widget: QWidget
        if mode == "table":
            try:
                from .views.table_view import TableView
                table_view = TableView(self._view_stack)
                suffix = Path(path).suffix.lower()
                if suffix in (".xlsx", ".xls"):
                    table_view.compare_excel(str(left_file), str(right_file))
                else:
                    table_view.compare_csv(str(left_file), str(right_file))
                widget = table_view
                label = f"Table: {Path(path).name}"
            except ImportError:
                # Fallback to text view if table_view not available
                text_view = TextView(self._view_stack)
                self._configure_text_view(text_view)
                text_view.compare_files(str(left_file), str(right_file))
                widget = text_view
                label = f"Text: {Path(path).name}"
        elif mode == "text":
            text_view = TextView(self._view_stack)
            self._configure_text_view(text_view)
            text_view.compare_files(str(left_file), str(right_file))
            widget = text_view
            label = f"Text: {Path(path).name}"
        elif mode == "image":
            image_view = ImageView(self._view_stack)
            image_view.compare_images(str(left_file), str(right_file))
            widget = image_view
            label = f"Image: {Path(path).name}"
        else:
            hex_view = HexView(self._view_stack)
            hex_view.compare_files(str(left_file), str(right_file))
            widget = hex_view
            label = f"Hex: {Path(path).name}"

        index = self._view_stack.addWidget(widget)
        self._document_tabs.add_document(label, index)
        self._file_compare_tabs[tab_key] = index
        self._switch_view(index)
        self._notify(f"Opened {label}", 4000)
        log_info("file compare tab opened", rel_path=path, mode=mode, index=index)

    def _determine_file_compare_mode(self, rel_path: str) -> str:
        name = Path(rel_path).name
        patterns = self._file_options.get("binary_patterns", [])
        if isinstance(patterns, list) and any(
            isinstance(pattern, str) and fnmatch(name, pattern)
            for pattern in patterns
        ):
            return "hex"
        suffix = Path(rel_path).suffix.lower()
        if suffix in TABLE_EXTENSIONS:
            return "table"
        if suffix in TEXT_EXTENSIONS:
            return "text"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        return "hex"

    def _configure_text_view(self, view: TextView) -> None:
        """Apply persisted file decoding and EOL options to a text view."""
        view.set_file_options(
            str(self._file_options.get("encoding", "utf-8")),
            bool(self._file_options.get("ignore_eol", True)),
        )

    def _resolve_compare_file_paths(self, rel_path: str) -> Optional[tuple[Path, Path]]:
        left_root = Path(self._left_path)
        right_root = Path(self._right_path)
        if not left_root.exists() or not right_root.exists():
            return None

        try:
            left_file = resolve_safe_relative(left_root, rel_path)
            right_file = resolve_safe_relative(right_root, rel_path)
        except UnsafePathError:
            return None
        if not left_file.exists() or not right_file.exists():
            return None
        if left_file.is_dir() or right_file.is_dir():
            return None
        return left_file, right_file

    def _make_file_tab_key(self, mode: str, left_file: Path, right_file: Path) -> str:
        return f"{mode}|{left_file.resolve()}|{right_file.resolve()}"

    # ------------------------------------------------------------------
    # 3-Way toggle
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_three_way_toggled(self, checked: bool) -> None:
        """Enable three-way mode and reveal the base-path row.

        The merge view is built at a fixed stack index during construction, so
        this no longer has to lazily create it -- and the sidebar's 3-Way Merge
        destination works whether or not this toggle has ever been used.
        """
        self._three_way_mode = checked
        self._path_bar.set_three_way_mode(checked)
        self._current_session().three_way_mode = checked
        self._notify(
            "Three-way mode enabled. Set a base folder to merge."
            if checked
            else "Three-way mode disabled.",
            5000,
        )
        self._update_action_states()

    @Slot(bool)
    def _on_preview_toggled(self, checked: bool) -> None:
        self._folder_view.set_preview_visible(checked)
        self._folder_view.set_preview_roots(self._left_path, self._right_path)

    # ------------------------------------------------------------------
    # Copy actions
    # ------------------------------------------------------------------

    @Slot()
    def _on_copy_lr(self) -> None:
        self._copy_selected_paths(left_to_right=True)

    @Slot()
    def _on_copy_rl(self) -> None:
        self._copy_selected_paths(left_to_right=False)

    # ------------------------------------------------------------------
    # Folder context-menu commands
    # ------------------------------------------------------------------

    @Slot(str, str, str)
    def _on_folder_context_command(self, command: str, rel_path: str, side: str) -> None:
        """Handle right-click menu commands from FolderView."""
        if command == "copy_lr":
            self._copy_paths([rel_path], left_to_right=True)
            return
        if command == "copy_rl":
            self._copy_paths([rel_path], left_to_right=False)
            return
        if command == "open_ext":
            self._open_external_for_path(rel_path, side)
            return
        if command == "open_new_view" or command == "compare_contents":
            self._on_file_activated(rel_path, False)
            return
        if command == "set_base_folder":
            self._set_base_folder_from_side(rel_path, side, other_side=False)
            return
        if command == "set_base_other":
            self._set_base_folder_from_side(rel_path, side, other_side=True)
            return
        if command == "copy_to_folder":
            self._copy_to_folder(rel_path, side)
            return
        if command == "move_to_folder":
            self._move_to_folder(rel_path, side)
            return
        if command == "delete_item":
            self._delete_item(rel_path, side)
            return
        if command == "rename_item":
            self._rename_item(rel_path, side)
            return
        if command == "attributes":
            self._show_item_attributes(rel_path, side)
            return
        if command == "touch_item":
            self._touch_item(rel_path, side)
            return
        if command == "exclude_item":
            self._exclude_item(rel_path)
            return
        if command == "new_folder":
            self._create_new_folder(rel_path, side)
            return
        if command == "copy_filename":
            self._copy_filename(rel_path)
            return
        if command == "ignored_toggle":
            self._toggle_ignored(rel_path)
            return
        if command == "refresh_selection":
            self._on_refresh()
            return
        if command == "sync_dialog":
            self._on_sync()
            return
        if command == "align_with":
            self._open_align_dialog(rel_path, side)
            return

    def _copy_selected_paths(self, *, left_to_right: bool) -> None:
        selected = self._folder_view.selected_paths()
        if not selected:
            QMessageBox.information(self, "No Selection", "No items selected.")
            return
        self._copy_paths(selected, left_to_right=left_to_right)

    def _copy_paths(self, rel_paths: list[str], *, left_to_right: bool) -> None:
        left_root = Path(self._left_path)
        right_root = Path(self._right_path)
        log_info(
            "copy requested",
            direction="left_to_right" if left_to_right else "right_to_left",
            count=len(rel_paths),
        )

        if not left_root.is_dir() or not right_root.is_dir():
            log_warning("copy rejected: non-local roots", left=self._left_path, right=self._right_path)
            QMessageBox.warning(
                self,
                "Copy Not Supported",
                "Copy is only supported for local directory comparisons.",
            )
            return

        try:
            for rel_path in rel_paths:
                resolve_safe_relative(left_root, rel_path)
                resolve_safe_relative(right_root, rel_path)
        except UnsafePathError as exc:
            log_warning("copy rejected: unsafe path", details=str(exc))
            QMessageBox.critical(self, "Unsafe Path", str(exc))
            return

        if self._cli_bridge is not None:
            direction = "left_to_right" if left_to_right else "right_to_left"
            if self._copy_worker is not None and self._copy_worker.is_running():
                self._copy_worker.cancel()

            args = self._cli_bridge.build_copy_args(
                left=self._left_path,
                right=self._right_path,
                direction=direction,
                paths=rel_paths,
                dry_run=False,
            )
            cmd = self._cli_bridge.build_command(args)

            self._copy_worker = CliJsonWorker(self)
            self._copy_worker.finished.connect(
                lambda report: self._on_copy_finished(report, left_to_right=left_to_right)
            )
            self._copy_worker.error.connect(
                lambda message: self._on_copy_error(message, rel_paths=rel_paths, left_to_right=left_to_right)
            )
            self._notify("Copying...")
            self._copy_worker.start(cmd)
            return

        self._copy_paths_local_fallback(rel_paths, left_to_right=left_to_right)

    def _on_copy_finished(self, report: dict, *, left_to_right: bool) -> None:
        if self._closing:
            return
        summary = report.get("summary", {})
        copied = int(summary.get("copied", 0))
        missing = int(summary.get("missing", 0))
        skipped = int(summary.get("skipped", 0))
        failed = int(summary.get("failed", 0))
        direction = "left_to_right" if left_to_right else "right_to_left"
        label = "Left -> Right" if left_to_right else "Right -> Left"
        self._notify(
            f"Copied {copied} item(s), {missing} missing, {skipped} skipped, "
            f"{failed} failed ({label})",
            8000,
        )
        log_info(
            "copy completed via cli",
            copied=copied,
            missing=missing,
            skipped=skipped,
            failed=failed,
            direction=direction,
        )
        self._on_refresh()

    def _on_copy_error(self, message: str, *, rel_paths: list[str], left_to_right: bool) -> None:
        """Report an ambiguous mutation failure without replaying it.

        The CLI may have completed some copies before returning an error.
        Automatically running a second implementation can overwrite newer data
        or repeat work against stale state.
        """
        if self._closing:
            return
        log_warning("copy via cli failed", error=message)
        self._notify(
            "Copy failed; refreshing to show any partial changes.",
            9000,
        )
        QMessageBox.critical(
            self,
            "Copy Failed",
            f"{message}\n\nThe operation was not retried because it may have "
            "completed partially. The comparison will be refreshed.",
        )
        self._on_refresh()

    def _copy_paths_local_fallback(self, rel_paths: list[str], *, left_to_right: bool) -> None:
        left_root = Path(self._left_path)
        right_root = Path(self._right_path)
        copied = 0
        missing = 0
        failed = 0

        for rel_path in rel_paths:
            try:
                source = resolve_safe_relative(
                    left_root if left_to_right else right_root, rel_path
                )
                target = resolve_safe_relative(
                    right_root if left_to_right else left_root, rel_path
                )
            except UnsafePathError:
                failed += 1
                continue

            if not source.exists():
                missing += 1
                continue

            try:
                if source.is_dir():
                    shutil.copytree(source, target, dirs_exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                copied += 1
            except OSError:
                failed += 1

        direction = "Left -> Right" if left_to_right else "Right -> Left"
        self._notify(
            f"Copied {copied} item(s), {missing} missing, {failed} failed ({direction})",
            7000,
        )
        log_info(
            "copy completed via local fallback",
            copied=copied,
            missing=missing,
            failed=failed,
            direction=direction,
        )
        self._on_refresh()

    def _sync_copy_path(self, source: Path, target: Path) -> None:
        """Copy one source path to target path (file or directory)."""
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def _sync_delete_path(self, target: Path, *, use_trash: bool, trash_root: Path) -> None:
        """Delete one target path, optionally moving it to a local trash folder."""
        if not target.exists():
            return

        if use_trash:
            trash_target = trash_root / target.name
            if trash_target.exists():
                stem = target.stem if target.stem else target.name
                suffix = target.suffix
                i = 1
                while (trash_root / f"{stem}_{i}{suffix}").exists():
                    i += 1
                trash_target = trash_root / f"{stem}_{i}{suffix}"
            shutil.move(str(target), str(trash_target))
            return

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def _plan_sync_actions(self, direction: str) -> list[tuple[str, str]]:
        """Build sync operations from the current report.

        Returns tuples of (action_code, relative_path).
        """
        report = self._current_report
        if report is None:
            return []

        actions: list[tuple[str, str]] = []
        for entry in sorted(report.entries, key=lambda e: e.path):
            status = entry.status
            rel_path = entry.path

            if status == DiffStatus.SAME:
                continue
            if status == DiffStatus.UNCHECKED:
                actions.append(("SKIP", rel_path))
                continue

            if direction == "left_to_right":
                if status == DiffStatus.ORPHAN_LEFT:
                    actions.append(("COPY_LR", rel_path))
                elif status == DiffStatus.ORPHAN_RIGHT:
                    actions.append(("DELETE_R", rel_path))
                elif status == DiffStatus.DIFFERENT:
                    actions.append(("UPDATE_R", rel_path))
                continue

            if direction == "right_to_left":
                if status == DiffStatus.ORPHAN_RIGHT:
                    actions.append(("COPY_RL", rel_path))
                elif status == DiffStatus.ORPHAN_LEFT:
                    actions.append(("DELETE_L", rel_path))
                elif status == DiffStatus.DIFFERENT:
                    actions.append(("UPDATE_L", rel_path))
                continue

            # bidirectional
            if status == DiffStatus.ORPHAN_LEFT:
                actions.append(("COPY_LR", rel_path))
            elif status == DiffStatus.ORPHAN_RIGHT:
                actions.append(("COPY_RL", rel_path))
            elif status == DiffStatus.DIFFERENT:
                left_m = entry.left.modified_unix if entry.left else None
                right_m = entry.right.modified_unix if entry.right else None
                if left_m is not None and right_m is not None:
                    if left_m > right_m:
                        actions.append(("COPY_LR", rel_path))
                    elif right_m > left_m:
                        actions.append(("COPY_RL", rel_path))
                    else:
                        actions.append(("CONFLICT", rel_path))
                else:
                    actions.append(("CONFLICT", rel_path))

        return actions

    @Slot(str, bool, bool)
    def _on_sync_requested(self, direction: str, dry_run: bool, use_trash: bool) -> None:
        """Execute synchronization actions selected in SyncDialog."""
        log_info(
            "sync requested",
            direction=direction,
            dry_run=dry_run,
            use_trash=use_trash,
        )
        if self._current_report is None:
            log_warning("sync rejected: no comparison report")
            QMessageBox.information(
                self,
                "No Comparison Available",
                "Run a comparison first before executing synchronization.",
            )
            return

        # Prefer CLI backend so sync behavior stays consistent with scan logic.
        if self._cli_bridge is not None:
            if self._sync_worker is not None and self._sync_worker.is_running():
                self._sync_worker.cancel()

            args = self._cli_bridge.build_sync_args(
                left=self._left_path,
                right=self._right_path,
                direction=direction,
                dry_run=dry_run,
                use_trash=use_trash,
                ignore_patterns=list(self._settings.ignore_patterns),
                follow_symlinks=self._settings.follow_symlinks,
                verify_hashes=self._settings.use_hash_verification,
                conflict="newest",
            )
            cmd = self._cli_bridge.build_command(args)

            self._sync_worker = CliJsonWorker(self)
            self._sync_worker.finished.connect(
                lambda report: self._on_sync_finished(report, dry_run=dry_run)
            )
            self._sync_worker.error.connect(
                lambda message: self._on_sync_error(
                    message, direction=direction, dry_run=dry_run, use_trash=use_trash
                )
            )
            self._notify("Sync dry-run..." if dry_run else "Syncing...")
            self._sync_worker.start(cmd)
            return

        self._sync_local_fallback(direction, dry_run, use_trash)

    def _on_sync_finished(self, report: dict, *, dry_run: bool) -> None:
        if self._closing:
            return
        summary = report.get("summary", {})
        copied = int(summary.get("copied", 0))
        updated = int(summary.get("updated", 0))
        deleted = int(summary.get("deleted", 0))
        skipped = int(summary.get("skipped", 0))
        failed = int(summary.get("failed", 0))
        label = "Sync dry-run" if dry_run else "Sync complete"
        self._notify(
            f"{label}: {copied} copied, {updated} updated, {deleted} deleted, "
            f"{skipped} skipped, {failed} failed.",
            10000,
        )
        log_info(
            "sync completed via cli",
            copied=copied,
            updated=updated,
            deleted=deleted,
            skipped=skipped,
            failed=failed,
            dry_run=dry_run,
        )
        if not dry_run:
            self._on_refresh()

    def _on_sync_error(self, message: str, *, direction: str, dry_run: bool, use_trash: bool) -> None:
        """Report a failed sync without replaying an unknown partial mutation."""
        if self._closing:
            return
        log_warning("sync via cli failed", error=message)
        self._notify(
            "Synchronization failed; refreshing to show any partial changes.",
            9000,
        )
        QMessageBox.critical(
            self,
            "Synchronization Failed",
            f"{message}\n\nThe operation was not retried because it may have "
            "completed partially. The comparison will be refreshed.",
        )
        self._on_refresh()

    def _sync_local_fallback(self, direction: str, dry_run: bool, use_trash: bool) -> None:
        left_root = Path(self._left_path)
        right_root = Path(self._right_path)
        if not left_root.is_dir() or not right_root.is_dir():
            log_warning("sync rejected: non-local roots", left=self._left_path, right=self._right_path)
            QMessageBox.warning(
                self,
                "Sync Not Supported",
                "Synchronization currently supports local directory paths only.",
            )
            return

        actions = self._plan_sync_actions(direction)
        if not actions:
            log_info("sync has no actions")
            self._notify("No synchronization actions required.", 5000)
            return

        if dry_run:
            copy_count = sum(1 for code, _ in actions if code in {"COPY_LR", "COPY_RL"})
            update_count = sum(1 for code, _ in actions if code in {"UPDATE_L", "UPDATE_R"})
            delete_count = sum(1 for code, _ in actions if code in {"DELETE_L", "DELETE_R"})
            skipped = sum(1 for code, _ in actions if code in {"SKIP", "CONFLICT"})
            self._notify(
                f"Sync dry-run: {copy_count} copy, {update_count} update, "
                f"{delete_count} delete, {skipped} skipped.",
                9000,
            )
            log_info(
                "sync dry-run completed via local planner",
                copy_count=copy_count,
                update_count=update_count,
                delete_count=delete_count,
                skipped=skipped,
            )
            return

        copied = 0
        updated = 0
        deleted = 0
        skipped = 0
        failed = 0

        trash_root = (left_root if direction == "right_to_left" else right_root) / ".rcompare_trash"
        if use_trash:
            trash_root.mkdir(parents=True, exist_ok=True)

        for code, rel_path in actions:
            try:
                left_path = resolve_safe_relative(left_root, rel_path)
                right_path = resolve_safe_relative(right_root, rel_path)
            except UnsafePathError:
                failed += 1
                continue

            try:
                if code == "COPY_LR":
                    if left_path.exists():
                        self._sync_copy_path(left_path, right_path)
                        copied += 1
                    else:
                        failed += 1
                elif code == "COPY_RL":
                    if right_path.exists():
                        self._sync_copy_path(right_path, left_path)
                        copied += 1
                    else:
                        failed += 1
                elif code == "UPDATE_R":
                    if left_path.exists():
                        self._sync_copy_path(left_path, right_path)
                        updated += 1
                    else:
                        failed += 1
                elif code == "UPDATE_L":
                    if right_path.exists():
                        self._sync_copy_path(right_path, left_path)
                        updated += 1
                    else:
                        failed += 1
                elif code == "DELETE_R":
                    self._sync_delete_path(right_path, use_trash=use_trash, trash_root=trash_root)
                    deleted += 1
                elif code == "DELETE_L":
                    self._sync_delete_path(left_path, use_trash=use_trash, trash_root=trash_root)
                    deleted += 1
                else:
                    skipped += 1
            except OSError:
                failed += 1

        self._notify(
            f"Sync complete: {copied} copied, {updated} updated, {deleted} deleted, "
            f"{skipped} skipped, {failed} failed.",
            10000,
        )
        log_info(
            "sync completed via local fallback",
            copied=copied,
            updated=updated,
            deleted=deleted,
            skipped=skipped,
            failed=failed,
        )
        self._on_refresh()

    def _open_external_for_path(self, rel_path: str, side: str) -> None:
        left_root = Path(self._left_path)
        right_root = Path(self._right_path)
        try:
            preferred = resolve_safe_relative(
                left_root if side == "left" else right_root, rel_path
            )
            fallback = resolve_safe_relative(
                right_root if side == "left" else left_root, rel_path
            )
        except UnsafePathError as exc:
            QMessageBox.critical(self, "Unsafe Path", str(exc))
            return

        target = preferred if preferred.exists() else fallback
        if not target.exists():
            QMessageBox.warning(
                self,
                "Open Failed",
                f"Path does not exist on either side:\n{rel_path}",
            )
            return

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        if not opened:
            QMessageBox.warning(
                self,
                "Open Failed",
                f"Could not open:\n{target}",
            )

    def _side_root(self, side: str) -> Path:
        return Path(self._left_path if side == "left" else self._right_path)

    def _other_side(self, side: str) -> str:
        return "right" if side == "left" else "left"

    def _resolve_item_path(self, rel_path: str, side: str, *, allow_fallback: bool) -> Optional[Path]:
        try:
            primary = resolve_safe_relative(self._side_root(side), rel_path)
        except UnsafePathError:
            return None
        if primary.exists():
            return primary
        if allow_fallback:
            try:
                secondary = resolve_safe_relative(
                    self._side_root(self._other_side(side)), rel_path
                )
            except UnsafePathError:
                return None
            if secondary.exists():
                return secondary
        return None

    def _set_base_folder_from_side(self, rel_path: str, side: str, *, other_side: bool) -> None:
        effective_side = self._other_side(side) if other_side else side
        try:
            base = resolve_safe_relative(self._side_root(effective_side), rel_path)
        except UnsafePathError as exc:
            QMessageBox.critical(self, "Unsafe Path", str(exc))
            return
        if base.exists() and base.is_file():
            base = base.parent
        elif not base.exists():
            base = base.parent
        if not base.exists():
            base = self._side_root(effective_side)

        self._base_path = str(base)
        self._path_bar.base_path = self._base_path
        self._current_session().base_path = self._base_path
        self._notify(f"Base folder set to: {base}", 6000)

    def _copy_to_folder(self, rel_path: str, side: str) -> None:
        source = self._resolve_item_path(rel_path, side, allow_fallback=True)
        if source is None:
            QMessageBox.warning(self, "Copy to Folder", "Source path does not exist.")
            return

        destination_dir = QFileDialog.getExistingDirectory(
            self,
            "Copy to Folder",
            str(source.parent),
        )
        if not destination_dir:
            return

        target = Path(destination_dir) / source.name
        try:
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            self._notify(f"Copied to: {target}", 7000)
        except OSError as exc:
            QMessageBox.critical(self, "Copy to Folder Failed", str(exc))

    def _move_to_folder(self, rel_path: str, side: str) -> None:
        source = self._resolve_item_path(rel_path, side, allow_fallback=False)
        if source is None:
            QMessageBox.warning(self, "Move to Folder", "Source path does not exist on this side.")
            return

        destination_dir = QFileDialog.getExistingDirectory(
            self,
            "Move to Folder",
            str(source.parent),
        )
        if not destination_dir:
            return

        target = Path(destination_dir) / source.name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            self._notify(f"Moved to: {target}", 7000)
            self._on_refresh()
        except OSError as exc:
            QMessageBox.critical(self, "Move to Folder Failed", str(exc))

    def _delete_item(self, rel_path: str, side: str) -> None:
        target = self._resolve_item_path(rel_path, side, allow_fallback=False)
        if target is None:
            QMessageBox.warning(self, "Delete", "Target path does not exist on this side.")
            return

        answer = QMessageBox.question(
            self,
            "Delete Item",
            f"Delete this item?\n{target}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            # Create backup for undo
            backup = create_backup(target, self._undo_history.backup_dir)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            self._record_file_op("delete", str(target), "", str(backup))
            self._notify(f"Deleted: {target}", 7000)
            self._on_refresh()
        except OSError as exc:
            QMessageBox.critical(self, "Delete Failed", str(exc))

    def _rename_item(self, rel_path: str, side: str) -> None:
        target = self._resolve_item_path(rel_path, side, allow_fallback=False)
        if target is None:
            QMessageBox.warning(self, "Rename", "Target path does not exist on this side.")
            return

        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=target.name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return

        renamed = target.with_name(new_name)
        try:
            target.rename(renamed)
            self._notify(f"Renamed to: {renamed.name}", 7000)
            self._on_refresh()
        except OSError as exc:
            QMessageBox.critical(self, "Rename Failed", str(exc))

    def _show_item_attributes(self, rel_path: str, side: str) -> None:
        target = self._resolve_item_path(rel_path, side, allow_fallback=True)
        if target is None:
            QMessageBox.warning(self, "Attributes", "Path does not exist.")
            return

        try:
            stat = target.stat()
        except OSError as exc:
            QMessageBox.critical(self, "Attributes Failed", str(exc))
            return

        lines = [
            f"Path: {target}",
            f"Type: {'Directory' if target.is_dir() else 'File'}",
            f"Size: {stat.st_size} bytes",
            f"Modified: {stat.st_mtime}",
            f"Mode: {oct(stat.st_mode)}",
        ]
        QMessageBox.information(self, "Attributes", "\n".join(lines))

    def _touch_item(self, rel_path: str, side: str) -> None:
        target = self._resolve_item_path(rel_path, side, allow_fallback=False)
        if target is None:
            QMessageBox.warning(self, "Touch", "Target path does not exist on this side.")
            return

        other = self._resolve_item_path(rel_path, self._other_side(side), allow_fallback=False)

        choices = ["Set to current time"]
        if other is not None and other.exists():
            choices.insert(0, "Copy timestamp from other side")

        choice, ok = QInputDialog.getItem(
            self, "Touch", f"Set timestamp for:\n{target.name}", choices, 0, False,
        )
        if not ok:
            return

        try:
            if choice == "Copy timestamp from other side" and other is not None:
                stat = other.stat()
                os.utime(target, (stat.st_atime, stat.st_mtime))
                self._notify(
                    f"Timestamp copied from {self._other_side(side)} side: {target.name}", 5000,
                )
            else:
                os.utime(target, None)
                self._notify(f"Touched: {target.name}", 5000)
            self._on_refresh()
        except OSError as exc:
            QMessageBox.critical(self, "Touch Failed", str(exc))

    def _exclude_item(self, rel_path: str) -> None:
        rel = rel_path.strip()
        if not rel:
            return
        patterns = list(self._settings.ignore_patterns)
        if rel not in patterns:
            patterns.append(rel)
            self._settings.ignore_patterns = patterns
            self._current_session().settings.ignore_patterns = list(patterns)
            self._notify(f"Excluded: {rel}", 6000)
            self._on_refresh()

    def _toggle_ignored(self, rel_path: str) -> None:
        rel = rel_path.strip()
        if not rel:
            return
        patterns = list(self._settings.ignore_patterns)
        if rel in patterns:
            patterns = [p for p in patterns if p != rel]
            self._notify(f"Removed from ignored: {rel}", 6000)
        else:
            patterns.append(rel)
            self._notify(f"Added to ignored: {rel}", 6000)
        self._settings.ignore_patterns = patterns
        self._current_session().settings.ignore_patterns = list(patterns)
        self._on_refresh()

    def _create_new_folder(self, rel_path: str, side: str) -> None:
        try:
            base = resolve_safe_relative(self._side_root(side), rel_path)
        except UnsafePathError as exc:
            QMessageBox.critical(self, "Unsafe Path", str(exc))
            return
        if base.exists() and base.is_file():
            base = base.parent
        elif not base.exists():
            base = base.parent
        base.mkdir(parents=True, exist_ok=True)

        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok:
            return
        try:
            name = validate_child_name(name)
        except UnsafePathError as exc:
            QMessageBox.warning(self, "Invalid Folder Name", str(exc))
            return

        target = base / name
        try:
            target.mkdir(parents=True, exist_ok=False)
            self._notify(f"Created folder: {target}", 6000)
            self._on_refresh()
        except FileExistsError:
            QMessageBox.warning(self, "New Folder", f"Folder already exists:\n{target}")
        except OSError as exc:
            QMessageBox.critical(self, "New Folder Failed", str(exc))

    def _open_align_dialog(self, rel_path: str, side: str) -> None:
        """Open the alignment dialog to manually align a file with another."""
        try:
            from .dialogs.align_dialog import AlignDialog
        except ImportError:
            QMessageBox.information(self, "Align With", "Alignment dialog not available yet.")
            return

        other_side = self._other_side(side)
        other_root = self._side_root(other_side)
        if not other_root.exists():
            return

        # Gather candidate files from the other side
        candidates: list[str] = []
        for item in sorted(other_root.rglob("*")):
            if item.is_file():
                candidates.append(str(item.relative_to(other_root)))

        filename = Path(rel_path).name
        dialog = AlignDialog(filename, candidates, parent=self)
        if dialog.exec():
            selected = dialog.selected_path()
            if selected:
                self._notify(
                    f"Aligned '{filename}' with '{selected}'", 5000,
                )
                log_info("alignment override", source=rel_path, target=selected, side=side)

    def _copy_filename(self, rel_path: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(Path(rel_path).name)
        self._notify("Filename copied to clipboard.", 4000)

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    @Slot()
    def _on_sync(self) -> None:
        """Open the Sync dialog."""
        if self._current_report is None:
            QMessageBox.information(
                self,
                "No Comparison Available",
                "Run a comparison first to generate a synchronization preview.",
            )
            return

        dialog = SyncDialog(self)
        dialog.set_preview_source(self._current_report, self._left_path, self._right_path)
        dialog.sync_requested.connect(self._on_sync_requested)
        dialog.exec()

    @Slot()
    def _on_save_profile(self) -> None:
        """Save the current session as a profile."""
        from .models.settings import SessionProfile

        profile = SessionProfile(
            name=f"Session - {self._left_path or 'untitled'}",
            left_path=self._left_path,
            right_path=self._right_path,
            base_path=self._base_path,
            ignore_patterns=list(self._settings.ignore_patterns),
            follow_symlinks=self._settings.follow_symlinks,
            hash_verification=self._settings.use_hash_verification,
        )
        if not self._profile_manager.add(profile):
            QMessageBox.warning(
                self,
                "Profile Not Saved",
                self._profile_manager.last_save_error
                or "The profile file could not be written.",
            )
            return
        self._notify(f"Profile '{profile.name}' saved.", 5000)
        log_info("profile saved", name=profile.name)

    def _save_profile_on_close(self) -> None:
        """Upsert an automatic profile snapshot for the active session."""
        if not self._left_path.strip() and not self._right_path.strip():
            return

        from datetime import datetime
        from .models.settings import SessionProfile

        existing = None
        for profile in self._profile_manager.profiles:
            if profile.name == _AUTO_CLOSE_PROFILE_NAME:
                existing = profile
                break

        now = datetime.now().isoformat()
        if existing is None:
            profile = SessionProfile(
                name=_AUTO_CLOSE_PROFILE_NAME,
                left_path=self._left_path,
                right_path=self._right_path,
                base_path=self._base_path,
                ignore_patterns=list(self._settings.ignore_patterns),
                follow_symlinks=self._settings.follow_symlinks,
                hash_verification=self._settings.use_hash_verification,
                last_used=now,
            )
            if not self._profile_manager.add(profile):
                log_warning(
                    "automatic profile was not saved",
                    details=self._profile_manager.last_save_error or "",
                )
            return

        existing.left_path = self._left_path
        existing.right_path = self._right_path
        existing.base_path = self._base_path
        existing.ignore_patterns = list(self._settings.ignore_patterns)
        existing.follow_symlinks = self._settings.follow_symlinks
        existing.hash_verification = self._settings.use_hash_verification
        existing.last_used = now
        if not self._profile_manager.update(existing):
            log_warning(
                "automatic profile was not updated",
                details=self._profile_manager.last_save_error or "",
            )

    @Slot()
    def _on_load_profile(self) -> None:
        """Open the Profiles dialog to load a session profile."""
        dialog = ProfilesDialog(
            self._profile_manager,
            left_path=self._left_path,
            right_path=self._right_path,
            base_path=self._base_path,
            ignore_patterns=list(self._settings.ignore_patterns),
            follow_symlinks=self._settings.follow_symlinks,
            hash_verification=self._settings.use_hash_verification,
            parent=self,
        )
        if dialog.exec():
            profile = dialog.selected_profile()
            if profile is not None:
                self._path_bar.left_path = profile.left_path
                self._path_bar.right_path = profile.right_path
                self._path_bar.base_path = profile.base_path
                self._left_path = profile.left_path
                self._right_path = profile.right_path
                self._base_path = profile.base_path
                self._settings.ignore_patterns = list(profile.ignore_patterns)
                self._settings.follow_symlinks = profile.follow_symlinks
                self._settings.use_hash_verification = profile.hash_verification
                session = self._current_session()
                session.left_path = profile.left_path
                session.right_path = profile.right_path
                session.base_path = profile.base_path
                session.settings = ComparisonSettings(
                    ignore_patterns=list(profile.ignore_patterns),
                    follow_symlinks=profile.follow_symlinks,
                    use_hash_verification=profile.hash_verification,
                    cache_dir=self._settings.cache_dir,
                )
                session.report = None
                session.status_summary = "Profile loaded"
                self._current_report = None
                self._folder_view.set_tree(
                    TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
                )
                self._update_active_session_title()
                self._notify(
                    f"Profile '{profile.name}' loaded.", 5000,
                )
                log_info("profile loaded", name=profile.name)

    def action_registry(self) -> list[QAction]:
        """Return every menu action, in menu order.

        The single source of truth for shortcuts: the About dialog renders its
        keyboard table from this list and tests/test_shortcuts.py checks it for
        collisions, so a hand-maintained second copy cannot drift again.
        """
        actions: list[QAction] = []
        seen: set[int] = set()
        for menu_action in self.menuBar().actions():
            menu = menu_action.menu()
            if menu is None:
                continue
            for action in menu.findChildren(QAction):
                if id(action) in seen or action.isSeparator():
                    continue
                seen.add(id(action))
                actions.append(action)
            for action in menu.actions():
                if id(action) in seen or action.isSeparator() or action.menu():
                    continue
                seen.add(id(action))
                actions.append(action)
        return actions

    def _apply_saved_shortcuts(self) -> None:
        """Apply persisted shortcut overrides after menu actions are built."""
        saved = self._config.shortcuts
        if not isinstance(saved, dict):
            return
        for action in self.action_registry():
            key = action.text().replace("&", "").strip()
            value = saved.get(key)
            if isinstance(value, str):
                action.setShortcut(QKeySequence(value))

    @Slot()
    def _on_about(self) -> None:
        """Open the About dialog with a keyboard table built from live actions."""
        dialog = AboutDialog(self, shortcuts=collect_shortcuts(self.action_registry()))
        dialog.exec()

    @Slot()
    def _on_close_tab(self) -> None:
        """Close the current session tab."""
        self._close_session(self._session_tab_bar.current_index)

    @Slot()
    def _on_find(self) -> None:
        """Focus the search field belonging to the *active* view."""
        widget = self._view_stack.currentWidget()
        focus_search = getattr(widget, "focus_search", None)
        if callable(focus_search):
            focus_search()
            return
        if self._view_stack.currentIndex() in _FOLDER_CONTEXT_VIEWS:
            self._integrated_status.focus_search()
            return
        self._notify("This view has no search field.", 4000)

    @Slot()
    def _on_find_next(self) -> None:
        """Advance the search in the active view, not always the folder tree."""
        self._navigate_search(forward=True)

    @Slot()
    def _on_find_prev(self) -> None:
        """Step the search back in the active view."""
        self._navigate_search(forward=False)

    def _navigate_search(self, *, forward: bool) -> None:
        """Route Find Next/Previous to whichever view is on screen.

        Both used to call into FolderView unconditionally, so pressing F3 in
        Text/Hex/Image/Table moved a selection the user could not see.
        """
        widget = self._view_stack.currentWidget()
        method = getattr(
            widget, "select_next_match" if forward else "select_prev_match", None
        )
        if not callable(method):
            self._notify("This view does not support Find Next/Previous.", 4000)
            return
        wrapped = method()
        if wrapped:
            self._notify(
                "Search wrapped to top." if forward else "Search wrapped to bottom.",
                3000,
            )

    # ------------------------------------------------------------------
    # Difference navigation
    # ------------------------------------------------------------------

    def _get_diff_entries(self) -> list:
        """Return entries from current report that are not identical.

        Cached against the current report object so repeated Next/Previous
        navigation doesn't re-filter the full entry list every time.
        """
        report = self._current_report
        if report is None:
            self._diff_entries_cache = None
            return []
        cached = self._diff_entries_cache
        if cached is not None and cached[0] is report:
            return cached[1]
        entries = [
            e for e in report.entries
            if e.status != DiffStatus.SAME and not (e.left and e.left.is_dir)
        ]
        self._diff_entries_cache = (report, entries, {e.path: i for i, e in enumerate(entries)})
        return entries

    def _get_all_file_entries(self) -> list:
        """Return all file entries from current report.

        Cached against the current report object; see _get_diff_entries().
        """
        report = self._current_report
        if report is None:
            self._all_file_entries_cache = None
            return []
        cached = self._all_file_entries_cache
        if cached is not None and cached[0] is report:
            return cached[1]
        entries = [
            e for e in report.entries
            if not (e.left and e.left.is_dir) or not (e.right and e.right.is_dir)
        ]
        self._all_file_entries_cache = (report, entries, {e.path: i for i, e in enumerate(entries)})
        return entries

    def _path_index(self, entries: list, cache: Optional[tuple], path: str) -> Optional[int]:
        """O(1) lookup of *path*'s index within *entries* using the cache
        populated by _get_diff_entries()/_get_all_file_entries(), falling
        back to a linear scan if the cache doesn't (yet) match.
        """
        if cache is not None and cache[1] is entries:
            return cache[2].get(path)
        try:
            return [e.path for e in entries].index(path)
        except ValueError:
            return None

    def _navigate_entry(self, entries: list, direction: int) -> None:
        """Navigate to next/prev entry in the given list."""
        if not entries:
            self._notify("No entries to navigate.", 3000)
            return

        # Get current selection
        selected = self._folder_view.selected_paths()
        current_path = selected[0] if selected else ""

        # Find current index
        current_idx = self._path_index(entries, self._diff_entries_cache, current_path)
        if current_idx is None:
            current_idx = self._path_index(entries, self._all_file_entries_cache, current_path)
        if current_idx is None:
            new_idx = 0 if direction > 0 else len(entries) - 1
        else:
            new_idx = current_idx + direction

        # Wrap around
        if new_idx >= len(entries):
            new_idx = 0
        elif new_idx < 0:
            new_idx = len(entries) - 1

        target_path = entries[new_idx].path
        self._folder_view.select_path(target_path)
        self._update_nav_status(new_idx, len(entries), entries[new_idx])

    def _update_nav_status(self, index: int, total: int, entry=None) -> None:
        """Update the status bar navigation indicators."""
        self._set_navigation_position(index + 1, total)

        # Also update file counter
        report = self._current_report
        if report:
            all_files = self._get_all_file_entries()
            if entry and entry.path:
                file_idx = self._path_index(all_files, self._all_file_entries_cache, entry.path)
                if file_idx is not None:
                    self._notify(
                        f"File {file_idx + 1} of {len(all_files)}: {entry.path}", 4000
                    )

    @Slot()
    def _on_prev_diff(self) -> None:
        """Navigate to the previous difference."""
        entries = self._get_diff_entries()
        self._navigate_entry(entries, -1)

    @Slot()
    def _on_next_diff(self) -> None:
        """Navigate to the next difference."""
        entries = self._get_diff_entries()
        self._navigate_entry(entries, 1)

    @Slot()
    def _on_prev_file(self) -> None:
        """Navigate to the previous file."""
        entries = self._get_all_file_entries()
        self._navigate_entry(entries, -1)

    @Slot()
    def _on_next_file(self) -> None:
        """Navigate to the next file."""
        entries = self._get_all_file_entries()
        self._navigate_entry(entries, 1)

    @Slot()
    def _on_apply_diff(self) -> None:
        """Apply selected difference: copy left -> right."""
        selected = self._folder_view.selected_paths()
        if not selected:
            self._notify("No item selected to apply.", 3000)
            return
        self._copy_paths(selected, left_to_right=True)

    @Slot()
    def _on_unapply_diff(self) -> None:
        """Unapply selected difference: copy right -> left."""
        selected = self._folder_view.selected_paths()
        if not selected:
            self._notify("No item selected to unapply.", 3000)
            return
        self._copy_paths(selected, left_to_right=False)

    @Slot()
    def _on_apply_all(self) -> None:
        """Apply all differences: copy all different/orphan items left -> right."""
        entries = self._get_diff_entries()
        if not entries:
            self._notify("No differences to apply.", 3000)
            return
        answer = QMessageBox.question(
            self,
            "Apply All",
            f"Apply all {len(entries)} difference(s) from left to right?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        paths = [e.path for e in entries]
        self._copy_paths(paths, left_to_right=True)

    @Slot()
    def _on_unapply_all(self) -> None:
        """Unapply all differences: copy all different/orphan items right -> left."""
        entries = self._get_diff_entries()
        if not entries:
            self._notify("No differences to unapply.", 3000)
            return
        answer = QMessageBox.question(
            self,
            "Unapply All",
            f"Unapply all {len(entries)} difference(s) from right to left?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        paths = [e.path for e in entries]
        self._copy_paths(paths, left_to_right=False)

    @Slot()
    def _on_diff_stats(self) -> None:
        """Show the Diff Statistics dialog."""
        if self._current_report is None:
            QMessageBox.information(
                self,
                "No Comparison Available",
                "Run a comparison first to see statistics.",
            )
            return
        dialog = StatsDialog(self._current_report, self)
        dialog.exec()

    # ------------------------------------------------------------------
    # File I/O: Open/Save diff, Print
    # ------------------------------------------------------------------

    @Slot()
    def _on_open_diff(self) -> None:
        """Open a diff/patch file and display it in the text view."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Diff File",
            "",
            "Diff files (*.diff *.patch);;All files (*)",
        )
        if not path:
            return

        try:
            content = Path(path).read_text(errors="replace")
        except OSError as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        # Display in text view
        self._switch_view(2)  # Text Compare tab (index 2 with Home at 0)
        self._text_view.show_diff_text(content, Path(path).name)
        self._notify(f"Opened diff: {path}", 5000)
        log_info("opened diff file", path=path)

    @Slot()
    def _on_compare_files_dialog(self) -> None:
        """Open a dialog to select two files/folders to compare."""
        left = pick_folder(self, "Select Left Folder", self._path_bar.left_path)
        if not left:
            return
        right = pick_folder(self, "Select Right Folder", self._path_bar.right_path)
        if not right:
            return
        self._path_bar.left_path = left
        self._path_bar.right_path = right
        self._on_compare()

    @Slot()
    def _on_save_diff(self) -> None:
        """Save the current comparison as a unified diff file."""
        if self._current_report is None:
            QMessageBox.information(
                self, "No Comparison", "Run a comparison first."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Diff",
            "comparison.diff",
            "Diff files (*.diff);;Patch files (*.patch);;All files (*)",
        )
        if not path:
            return

        try:
            lines = self._generate_diff_output()
            Path(path).write_text("\n".join(lines), encoding="utf-8")
            self._notify(f"Diff saved: {path}", 5000)
            log_info("diff saved", path=path)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _generate_diff_output(self) -> list[str]:
        """Generate a unified-diff-style text summary of the current comparison."""
        report = self._current_report
        if report is None:
            return []

        lines: list[str] = []
        lines.append(f"--- {report.left}")
        lines.append(f"+++ {report.right}")
        lines.append("# RCompare comparison report")
        lines.append(f"# Total: {report.summary.total} entries")
        lines.append(f"# Same: {report.summary.same}")
        lines.append(f"# Different: {report.summary.different}")
        lines.append(f"# Left only: {report.summary.orphan_left}")
        lines.append(f"# Right only: {report.summary.orphan_right}")
        lines.append("")

        for entry in sorted(report.entries, key=lambda e: e.path):
            status = entry.status
            if status == DiffStatus.SAME:
                lines.append(f"  {entry.path}")
            elif status == DiffStatus.DIFFERENT:
                left_size = entry.left.size if entry.left else "?"
                right_size = entry.right.size if entry.right else "?"
                lines.append(f"! {entry.path}  (left={left_size}, right={right_size})")
            elif status == DiffStatus.ORPHAN_LEFT:
                lines.append(f"- {entry.path}  (left only)")
            elif status == DiffStatus.ORPHAN_RIGHT:
                lines.append(f"+ {entry.path}  (right only)")
            elif status == DiffStatus.UNCHECKED:
                lines.append(f"? {entry.path}  (unchecked)")

        # Include text diffs if available
        if report.text_diffs:
            for td in report.text_diffs:
                lines.append("")
                lines.append(f"diff {td.path}")
                for line in td.lines:
                    ct = line.change_type.lower()
                    content = line.content
                    if ct == "insert":
                        lines.append(f"+{content}")
                    elif ct == "delete":
                        lines.append(f"-{content}")
                    else:
                        lines.append(f" {content}")

        return lines

    @Slot()
    def _on_save_all(self) -> None:
        """Save all modifications (apply all differences left -> right)."""
        self._on_apply_all()

    @Slot()
    def _on_print(self) -> None:
        """Print the current comparison view."""
        doc = self._build_print_document()
        if doc is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            doc.print_(printer)

    @Slot()
    def _on_print_preview(self) -> None:
        """Show print preview of the current comparison."""
        doc = self._build_print_document()
        if doc is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.paintRequested.connect(lambda p: doc.print_(p))
        preview.exec()

    def _build_print_document(self) -> Optional[QTextDocument]:
        """Build a QTextDocument from the current comparison for printing."""
        report = self._current_report
        if report is None:
            QMessageBox.information(
                self, "No Comparison", "Run a comparison first."
            )
            return None

        doc = QTextDocument()
        html_parts = [
            "<h2>RCompare Comparison Report</h2>",
            f"<p><b>Left:</b> {report.left}</p>",
            f"<p><b>Right:</b> {report.right}</p>",
            "<table border='1' cellpadding='4' cellspacing='0' width='100%'>",
            "<tr><th>Status</th><th>Path</th><th>Left Size</th><th>Right Size</th></tr>",
        ]

        status_labels = {
            DiffStatus.SAME: ("Identical", "#e8f5e9"),
            DiffStatus.DIFFERENT: ("Different", "#ffebee"),
            DiffStatus.ORPHAN_LEFT: ("Left Only", "#fff3e0"),
            DiffStatus.ORPHAN_RIGHT: ("Right Only", "#e3f2fd"),
            DiffStatus.UNCHECKED: ("Unchecked", "#f5f5f5"),
        }

        for entry in sorted(report.entries, key=lambda e: e.path):
            label, bg = status_labels.get(entry.status, ("?", "#ffffff"))
            left_size = str(entry.left.size) if entry.left else "-"
            right_size = str(entry.right.size) if entry.right else "-"
            html_parts.append(
                f"<tr style='background-color:{bg}'>"
                f"<td>{label}</td><td>{entry.path}</td>"
                f"<td align='right'>{left_size}</td><td align='right'>{right_size}</td></tr>"
            )

        html_parts.append("</table>")
        html_parts.append(
            f"<p><b>Summary:</b> {report.summary.same} identical, "
            f"{report.summary.different} different, "
            f"{report.summary.orphan_left} left only, "
            f"{report.summary.orphan_right} right only</p>"
        )
        doc.setHtml("\n".join(html_parts))
        return doc

    @Slot()
    def _on_profiles(self) -> None:
        """Open the Profiles dialog."""
        dialog = ProfilesDialog(
            self._profile_manager,
            left_path=self._left_path,
            right_path=self._right_path,
            base_path=self._base_path,
            ignore_patterns=self._settings.ignore_patterns,
            follow_symlinks=self._settings.follow_symlinks,
            hash_verification=self._settings.use_hash_verification,
            parent=self,
        )
        if dialog.exec():
            selected = dialog.selected_profile()
            if selected:
                self._apply_profile(selected)

    @Slot()
    def _on_preferences(self) -> None:
        """Open Settings and apply every field it exposes (WI-5.10).

        There used to be two handlers: this one, which was connected but
        dropped ``get_config_updates()`` (so Theme and CLI Path were silently
        discarded), and ``_on_options()``, which was more complete but wired to
        nothing. They are now one handler, and each Settings page round-trips.
        """
        dialog = SettingsDialog(self._config, self._settings, self)
        if not dialog.exec():
            return

        # -- General: comparison behaviour ---------------------------------
        self._settings = dialog.get_settings()
        self._current_session().settings = self._settings.copy()

        # -- Diff Options and Files -----------------------------------------
        # Both pages were pure decoration before: nothing read them back.
        self._diff_options = dialog.get_diff_options()
        self._file_options = dialog.get_file_options()
        self._config.diff_options = dict(self._diff_options)
        self._config.file_options = dict(self._file_options)
        for view in self.findChildren(TextView):
            self._configure_text_view(view)

        # -- Appearance ------------------------------------------------------
        appearance = dialog.get_appearance_settings()
        self._config.appearance = appearance
        self._apply_appearance(appearance)

        # -- Theme and CLI path ----------------------------------------------
        updates = dialog.get_config_updates()
        new_theme = str(updates.get("theme", self._config.theme))
        theme_changed = new_theme != self._config.theme
        self._config.theme = new_theme
        if theme_changed:
            # Applied live rather than "after restart": the selector previously
            # neither persisted nor took effect at all.
            apply_theme(QApplication.instance(), new_theme)

        new_cli_path = updates.get("cli_path")
        if new_cli_path != self._config.cli_path:
            self._config.cli_path = new_cli_path
            self._rebuild_cli_bridge()

        self._sync_config_from_runtime()
        self._config.save()
        self._notify("Settings saved.", 4000)
        self._update_action_states()

    def _rebuild_cli_bridge(self) -> None:
        """Recreate the CLI bridge after its configured path changed."""
        try:
            cli_path = self._config.get_cli_path()
        except FileNotFoundError as exc:
            self._cli_bridge = None
            log_warning("cli bridge unavailable after settings change", details=str(exc))
            QMessageBox.warning(
                self,
                "CLI Not Found",
                f"{exc}\n\nComparison is unavailable until a valid binary is set.",
            )
            return
        self._cli_bridge = CliBridge(cli_path)
        self._notify(f"Using rcompare_cli at {cli_path}", 5000)
        log_info("cli bridge rebuilt", cli_path=cli_path)

    def _scan_options(self) -> dict:
        """Translate the Settings pages into rcompare_cli scan arguments.

        Keeps the mapping in one place so a control added to Settings has an
        obvious place to become a real flag rather than dead UI.
        """
        diff = self._diff_options
        whitespace = str(diff.get("ignore_whitespace", "none")).lower()
        return {
            "text_diff": bool(diff.get("text_diff", True)),
            "image_diff": bool(diff.get("image_diff", False)),
            "image_exif": bool(diff.get("image_exif", False)),
            "csv_diff": bool(diff.get("csv_diff", False)),
            "excel_diff": bool(diff.get("excel_diff", False)),
            "json_diff": bool(diff.get("json_diff", False)),
            "yaml_diff": bool(diff.get("yaml_diff", False)),
            "ignore_whitespace": None if whitespace == "none" else whitespace,
            "ignore_case": bool(diff.get("ignore_case", False)),
            "regex_rules": list(diff.get("regex_rules", [])),
            "csv_key_columns": list(diff.get("csv_key_columns", [])),
        }

    @Slot()
    def _on_configure_shortcuts(self) -> None:
        """Open the Configure Keyboard Shortcuts dialog."""
        from .dialogs.shortcuts_dialog import ShortcutsDialog
        dialog = ShortcutsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._config.shortcuts = dialog.shortcut_map()
            self._config.save()
            self._notify("Keyboard shortcuts saved.", 4000)

    @Slot()
    def _on_handbook(self) -> None:
        """Open the online handbook."""
        url = "https://github.com/aecs4u/rcompare/wiki"
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(
                self,
                "Open Handbook",
                f"Could not open URL:\n{url}",
            )

    @Slot()
    def _on_report_bug(self) -> None:
        """Open the bug report page."""
        url = "https://github.com/aecs4u/rcompare/issues/new"
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(
                self,
                "Report Bug",
                f"Could not open URL:\n{url}",
            )

    @Slot()
    def _on_about_kde(self) -> None:
        """Show About KDE dialog."""
        QMessageBox.about(
            self,
            "About KDE",
            "<h3>About KDE</h3>"
            "<p>This application uses the Qt toolkit and follows KDE "
            "application conventions.</p>"
            "<p>Learn more about KDE at "
            '<a href="https://kde.org">https://kde.org</a></p>',
        )

    # ------------------------------------------------------------------
    # Close event -- persist geometry
    # ------------------------------------------------------------------

    def _can_close_documents(self) -> bool:
        """Give every editable comparison a chance to save or cancel closing."""
        seen: set[int] = set()
        for index in range(self._view_stack.count()):
            widget = self._view_stack.widget(index)
            if widget is None or id(widget) in seen:
                continue
            seen.add(id(widget))
            maybe_close = getattr(widget, "maybe_close", None)
            if callable(maybe_close) and not maybe_close():
                return False
        return True

    def _shutdown_workers(self) -> None:
        """Cancel all asynchronous work before child widgets are destroyed."""
        self._filter_timer.stop()
        for worker in (self._worker, self._copy_worker, self._sync_worker):
            if worker is not None:
                worker.cancel()
        for index in range(self._view_stack.count()):
            widget = self._view_stack.widget(index)
            cancel = getattr(widget, "cancel_pending", None)
            if callable(cancel):
                cancel()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Save window geometry to config before closing."""
        if not self._can_close_documents():
            event.ignore()
            return
        self._closing = True
        self._shutdown_workers()
        log_info("main window close event")
        self._capture_session_state(self._active_session_index)
        self._save_profile_on_close()
        geom = self.geometry()
        self._config.window_geometry = {
            "x": geom.x(),
            "y": geom.y(),
            "width": geom.width(),
            "height": geom.height(),
        }
        self._sync_config_from_runtime()
        self._config.save()
        log_info("configuration persisted on close")
        super().closeEvent(event)

    def _restore_persistent_state(self) -> None:
        """Restore last-used per-user settings/options from AppConfig."""
        if not self._sessions:
            self._sessions = [SessionState(name="Session 1")]
            if self._session_tab_bar.count == 0:
                self._session_tab_bar.add_session("Session 1")
            self._active_session_index = 0

        session = self._sessions[0]
        session.settings = ComparisonSettings.from_dict(
            self._config.comparison_settings
        )

        paths = self._config.last_paths or {}
        session.left_path = str(paths.get("left", ""))
        session.right_path = str(paths.get("right", ""))
        session.base_path = str(paths.get("base", ""))

        session.three_way_mode = bool(self._config.three_way_mode)

        filters = self._config.filter_options or {}
        session.filters = FolderFilterState.from_dict(filters)
        mode_value = filters.get("folder_view_mode", "compare_structure")
        session.folder_view_mode = (
            str(mode_value) if isinstance(mode_value, str) else "compare_structure"
        )
        session.always_show_folders = bool(filters.get("always_show_folders", True))
        session.status_summary = "Ready"
        session.report = None

        view_index = self._config.active_view
        session.active_view = view_index if isinstance(view_index, int) else 0
        if session.active_view < 0 or session.active_view >= _BASE_VIEW_COUNT:
            session.active_view = 0  # Home view

        self._session_tab_bar.current_index = 0
        self._apply_session_state(0)
        self._folder_view.set_column_widths(self._config.folder_columns or {})
        self._rebuild_bookmarks_menu()

    def _apply_appearance(self, appearance: dict) -> None:
        """Apply appearance settings to all text views."""
        self._text_view.apply_appearance(appearance)

    def _sync_config_from_runtime(self) -> None:
        """Write current runtime state into AppConfig before save."""
        self._config.comparison_settings = self._settings.to_dict()
        self._config.filter_options = {
            **self._filter_state.to_dict(),
            "folder_view_mode": self._folder_view_mode(),
            "always_show_folders": self._act_always_show_folders.isChecked(),
        }
        self._config.folder_columns = self._folder_view.column_widths()
        self._config.last_paths = {
            "left": self._left_path,
            "right": self._right_path,
            "base": self._base_path,
        }
        self._config.active_view = int(self._view_stack.currentIndex())
        self._config.three_way_mode = bool(self._three_way_mode)

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _update_undo_redo_state(self) -> None:
        self._act_undo.setEnabled(self._undo_history.can_undo)
        self._act_redo.setEnabled(self._undo_history.can_redo)

    def _record_file_op(self, op_type: str, source: str, dest: str, backup_path: str | None = None) -> None:
        """Record a file operation for undo."""
        from datetime import datetime
        op = Operation(
            op_type=op_type,
            source_path=source,
            dest_path=dest,
            backup_path=backup_path,
            timestamp=datetime.now().isoformat(),
        )
        self._undo_history.push(op)
        self._update_undo_redo_state()

    @Slot()
    def _on_undo(self) -> None:
        """Undo the last file operation."""
        from .models.undo_stack import restore_backup
        op = self._undo_history.undo()
        if op is None:
            return

        try:
            if op.backup_path and Path(op.backup_path).exists():
                restore_backup(Path(op.backup_path), Path(op.source_path))
                self._notify(f"Undone: {op.op_type} on {Path(op.source_path).name}", 5000)
            else:
                self._notify("Cannot undo: no backup available", 5000)
        except OSError as exc:
            QMessageBox.critical(self, "Undo Failed", str(exc))

        self._update_undo_redo_state()
        self._on_refresh()

    @Slot()
    def _on_redo(self) -> None:
        """Redo a previously undone operation."""
        op = self._undo_history.redo()
        if op is None:
            return
        target = Path(op.source_path)
        try:
            if op.op_type == "delete" and target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                self._notify(f"Redone: deleted {target.name}", 5000)
                self._on_refresh()
            else:
                self._notify(f"Cannot redo unsupported operation: {op.op_type}", 5000)
                self._undo_history.undo()
        except OSError as exc:
            self._undo_history.undo()
            QMessageBox.critical(self, "Redo Failed", str(exc))
        self._update_undo_redo_state()

    # ------------------------------------------------------------------
    # Drag-and-drop support
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Accept file/folder URL drops onto the main window."""
        mime: QMimeData = event.mimeData()
        if mime.hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Handle dropped files/folders — populate path bar and auto-compare."""
        mime: QMimeData = event.mimeData()
        if not mime.hasUrls():
            super().dropEvent(event)
            return

        paths: list[str] = []
        for url in mime.urls():
            local = url.toLocalFile()
            if local:
                paths.append(local)

        if not paths:
            return

        if len(paths) >= 2:
            self._set_left_path(paths[0])
            self._set_right_path(paths[1])
            if len(paths) > 2:
                # Silently discarding the rest left the user believing all of
                # them had been accepted.
                extra = len(paths) - 2
                self._notify(
                    f"Comparing the first two of {len(paths)} dropped paths; "
                    f"{extra} ignored ({', '.join(Path(p).name for p in paths[2:])}).",
                    9000,
                )
            else:
                self._notify("Dropped two paths — starting comparison...", 5000)
            self._on_compare()
        elif not self._left_path.strip():
            self._set_left_path(paths[0])
            self._notify(
                f"Left path set to: {paths[0]}  (drop another for the right side)",
                5000,
            )
        elif not self._right_path.strip():
            self._set_right_path(paths[0])
            self._notify("Right path set — starting comparison...", 5000)
            self._on_compare()
        else:
            self._set_left_path(paths[0])
            self._notify(
                f"Left path updated to: {paths[0]}  (drop another for the right side)",
                5000,
            )

        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # Profile helpers
    # ------------------------------------------------------------------

    def _apply_profile(self, profile) -> None:
        """Apply a loaded session profile to the current session."""
        self._path_bar.left_path = profile.left_path
        self._path_bar.right_path = profile.right_path
        self._path_bar.base_path = profile.base_path
        self._left_path = profile.left_path
        self._right_path = profile.right_path
        self._base_path = profile.base_path
        self._settings.ignore_patterns = list(profile.ignore_patterns)
        self._settings.follow_symlinks = profile.follow_symlinks
        self._settings.use_hash_verification = profile.hash_verification
        session = self._current_session()
        session.left_path = profile.left_path
        session.right_path = profile.right_path
        session.base_path = profile.base_path
        session.settings = ComparisonSettings(
            ignore_patterns=list(profile.ignore_patterns),
            follow_symlinks=profile.follow_symlinks,
            use_hash_verification=profile.hash_verification,
            cache_dir=self._settings.cache_dir,
        )
        session.report = None
        session.status_summary = "Profile loaded"
        self._current_report = None
        self._folder_view.set_tree(
            TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
        )
        self._update_active_session_title()
        self._notify(f"Profile '{profile.name}' loaded.", 5000)
        log_info("profile applied", name=profile.name)

    # ------------------------------------------------------------------
    # Bookmarks
    # ------------------------------------------------------------------

    @Slot()
    def _on_add_bookmark(self) -> None:
        """Add a bookmark for the current left+right path pair."""
        left = self._left_path.strip()
        right = self._right_path.strip()
        if not left and not right:
            QMessageBox.information(
                self, "Add Bookmark", "Set paths first before adding a bookmark."
            )
            return

        default_name = ""
        if left and right:
            default_name = f"{Path(left).name} <> {Path(right).name}"
        elif left:
            default_name = Path(left).name
        elif right:
            default_name = Path(right).name

        name, ok = QInputDialog.getText(
            self, "Add Bookmark", "Bookmark name:", text=default_name,
        )
        if not ok or not name.strip():
            return

        bookmark = {"name": name.strip(), "left": left, "right": right}
        self._config.bookmarks.append(bookmark)
        self._config.save()
        self._rebuild_bookmarks_menu()
        self._notify(f"Bookmark '{name.strip()}' added.", 5000)

    @Slot()
    def _on_manage_bookmarks(self) -> None:
        """Show a simple dialog to manage (delete) bookmarks."""
        bookmarks = self._config.bookmarks
        if not bookmarks:
            QMessageBox.information(self, "Bookmarks", "No bookmarks saved.")
            return

        names = [b.get("name", "Unnamed") for b in bookmarks]
        name, ok = QInputDialog.getItem(
            self, "Manage Bookmarks", "Select bookmark to remove:", names, 0, False,
        )
        if not ok:
            return

        idx = names.index(name)
        del self._config.bookmarks[idx]
        self._config.save()
        self._rebuild_bookmarks_menu()
        self._notify(f"Bookmark '{name}' removed.", 5000)

    def _rebuild_bookmarks_menu(self) -> None:
        """Rebuild the dynamic bookmark entries in the Bookmarks menu."""
        # Remove old dynamic entries (everything after the separator)
        actions = self._bookmarks_menu.actions()
        for action in actions[self._bookmarks_separator_index:]:
            self._bookmarks_menu.removeAction(action)

        for i, bookmark in enumerate(self._config.bookmarks):
            name = bookmark.get("name", f"Bookmark {i + 1}")
            left = bookmark.get("left", "")
            right = bookmark.get("right", "")
            action = QAction(name, self)
            action.setToolTip(f"{left} <> {right}")
            action.triggered.connect(
                lambda checked=False, left_path=left, right_path=right: self._load_bookmark(
                    left_path, right_path
                )
            )
            self._bookmarks_menu.addAction(action)

    def _load_bookmark(self, left: str, right: str) -> None:
        """Load a bookmarked path pair."""
        self._path_bar.left_path = left
        self._path_bar.right_path = right
        self._notify("Bookmark loaded.", 5000)
        if left and right:
            self._on_compare()
