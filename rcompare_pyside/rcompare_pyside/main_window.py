"""Main application window -- central orchestrator for the RCompare PySide6 frontend."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QTabBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .utils.config import AppConfig
from .utils.cli_bridge import CliBridge, DiffStatus, ScanReport
from .models.comparison import build_tree_with_options, TreeNode
from .models.settings import ComparisonSettings, ProfileManager
from .views.path_bar import PathBar
from .views.folder_view import FolderView
from .views.text_view import TextView
from .views.hex_view import HexView
from .views.image_view import ImageView
from .widgets.filter_bar import FilterBar
from .workers.comparison_worker import ComparisonWorker
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.sync_dialog import SyncDialog
from .dialogs.profiles_dialog import ProfilesDialog
from .dialogs.about_dialog import AboutDialog
from .utils.telemetry import log_error, log_info, log_warning

# ---------------------------------------------------------------------------
# File-type extension sets used for view switching on double-click
# ---------------------------------------------------------------------------
TEXT_EXTENSIONS = {
    ".txt", ".md", ".rs", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".c", ".cpp", ".h", ".hpp", ".java", ".go", ".rb", ".php",
    ".sh", ".css", ".html", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".sql", ".csv", ".log",
}

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif",
    ".webp", ".ico", ".svg",
}

_AUTO_CLOSE_PROFILE_NAME = "Last Session (Auto)"
_BASE_VIEW_TAB_COUNT = 4


@dataclass
class SessionState:
    """Per-tab session state."""

    name: str
    left_path: str = ""
    right_path: str = ""
    base_path: str = ""
    settings: ComparisonSettings = field(default_factory=ComparisonSettings)
    three_way_mode: bool = False
    show_identical: bool = True
    show_different: bool = True
    show_left_only: bool = True
    show_right_only: bool = True
    show_files_only: bool = False
    search_text: str = ""
    diff_option_mode: str = "show_differences"
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
        self._worker: Optional[ComparisonWorker] = None
        self._current_report: Optional[ScanReport] = None
        self._settings: ComparisonSettings = ComparisonSettings()
        self._profile_manager: ProfileManager = ProfileManager()
        self._three_way_mode: bool = False

        # Paths cached from the PathBar
        self._left_path: str = ""
        self._right_path: str = ""
        self._base_path: str = ""
        self._sessions: list[SessionState] = []
        self._active_session_index: int = -1
        self._file_compare_tabs: dict[str, int] = {}

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

        # --- Build UI --------------------------------------------------
        self._build_menu_bar()
        self._build_toolbar()
        self._build_central_widget()
        self._build_status_bar()

        # --- Signal wiring ---------------------------------------------
        self._connect_signals()
        self._restore_persistent_state()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _themed_icon(self, *names: str) -> QIcon:
        for name in names:
            icon = QIcon.fromTheme(name)
            if not icon.isNull():
                return icon
        return QIcon()

    def _build_menu_bar(self) -> None:
        menu_bar: QMenuBar = self.menuBar()

        # -- File -------------------------------------------------------
        file_menu = menu_bar.addMenu("&File")

        self._act_new_tab = QAction(self._themed_icon("tab-new"), "&New Tab", self)
        self._act_new_tab.setShortcut(QKeySequence.StandardKey.AddTab)  # Ctrl+T
        file_menu.addAction(self._act_new_tab)

        self._act_close_tab = QAction(self._themed_icon("tab-close"), "&Close Tab", self)
        self._act_close_tab.setShortcut(QKeySequence.StandardKey.Close)  # Ctrl+W
        file_menu.addAction(self._act_close_tab)

        file_menu.addSeparator()

        self._act_quit = QAction(self._themed_icon("application-exit"), "&Quit", self)
        self._act_quit.setShortcut(QKeySequence.StandardKey.Quit)  # Ctrl+Q
        file_menu.addAction(self._act_quit)

        # -- Edit -------------------------------------------------------
        edit_menu = menu_bar.addMenu("&Edit")

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
        self._act_sync.setShortcut(QKeySequence("Ctrl+Y"))
        tools_menu.addAction(self._act_sync)

        tools_menu.addSeparator()

        self._act_profiles = QAction(
            self._themed_icon("document-open"),
            "&Profiles...",
            self,
        )
        self._act_profiles.setShortcut(QKeySequence("Ctrl+P"))
        tools_menu.addAction(self._act_profiles)

        # -- Settings ---------------------------------------------------
        settings_menu = menu_bar.addMenu("&Settings")

        self._act_configure_shortcuts = QAction("Configure &Shortcuts...", self)
        self._act_configure_shortcuts.setShortcut(
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_Comma)
        )
        settings_menu.addAction(self._act_configure_shortcuts)

        self._act_configure_toolbars = QAction("Configure Tool&bars...", self)
        settings_menu.addAction(self._act_configure_toolbars)

        settings_menu.addSeparator()

        self._act_preferences = QAction(
            self._themed_icon("configure"),
            "Configure &rcompare...",
            self,
        )
        self._act_preferences.setShortcut(
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Comma)
        )
        settings_menu.addAction(self._act_preferences)

        # -- Help -------------------------------------------------------
        help_menu = menu_bar.addMenu("&Help")

        self._act_handbook = QAction(
            self._themed_icon("help-contents"),
            "rcompare &Handbook",
            self,
        )
        self._act_handbook.setShortcut(QKeySequence.StandardKey.HelpContents)  # F1
        help_menu.addAction(self._act_handbook)

        help_menu.addSeparator()

        self._act_report_bug = QAction("&Report Bug...", self)
        help_menu.addAction(self._act_report_bug)

        self._act_about = QAction(self._themed_icon("help-about"), "&About rcompare", self)
        help_menu.addAction(self._act_about)

        self._act_about_kde = QAction("About &KDE", self)
        help_menu.addAction(self._act_about_kde)

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        # Session / navigation
        self._tb_home = QAction(self._themed_icon("go-home"), "Home", self)
        toolbar.addAction(self._tb_home)

        self._tb_new = QAction(self._themed_icon("tab-new"), "Sessions", self)
        toolbar.addAction(self._tb_new)
        self._tb_profiles = QAction(self._themed_icon("document-open"), "Profiles", self)
        toolbar.addAction(self._tb_profiles)

        toolbar.addSeparator()
        # Quick status filter presets (ideas_for_toolbars)
        self._tb_filter_all = QAction("All", self)
        self._tb_filter_all.setCheckable(True)
        toolbar.addAction(self._tb_filter_all)

        self._tb_filter_diffs = QAction("Diffs", self)
        self._tb_filter_diffs.setCheckable(True)
        toolbar.addAction(self._tb_filter_diffs)

        self._tb_filter_same = QAction("Same", self)
        self._tb_filter_same.setCheckable(True)
        toolbar.addAction(self._tb_filter_same)

        toolbar.addSeparator()

        self._tb_compare = QAction(self._themed_icon("system-search"), "Compare", self)
        toolbar.addAction(self._tb_compare)

        self._tb_refresh = QAction(self._themed_icon("view-refresh"), "Refresh", self)
        self._tb_refresh.setShortcut(QKeySequence(Qt.Key.Key_F5))
        toolbar.addAction(self._tb_refresh)

        self._tb_swap = QAction(
            self._themed_icon("view-sort-descending", "object-flip-horizontal"),
            "Swap",
            self,
        )
        toolbar.addAction(self._tb_swap)

        self._tb_cancel = QAction(self._themed_icon("process-stop"), "Stop", self)
        self._tb_cancel.setEnabled(False)
        toolbar.addAction(self._tb_cancel)

        toolbar.addSeparator()

        # 3-Way toggle
        self._tb_three_way = QAction(self._themed_icon("view-split-left-right"), "3-Way", self)
        self._tb_three_way.setCheckable(True)
        toolbar.addAction(self._tb_three_way)

        toolbar.addSeparator()

        # Expand All / Collapse All
        self._tb_expand_all = QAction(self._themed_icon("zoom-in"), "Expand", self)
        toolbar.addAction(self._tb_expand_all)

        self._tb_collapse_all = QAction(self._themed_icon("zoom-out"), "Collapse", self)
        toolbar.addAction(self._tb_collapse_all)

        toolbar.addSeparator()

        # Copy actions
        self._tb_copy_lr = QAction(self._themed_icon("go-next"), "Copy", self)
        toolbar.addAction(self._tb_copy_lr)

        self._tb_copy_rl = QAction(self._themed_icon("go-previous"), "Copy <-", self)
        toolbar.addAction(self._tb_copy_rl)

        # Sync
        self._tb_sync = QAction(self._themed_icon("view-refresh"), "Synchronize", self)
        toolbar.addAction(self._tb_sync)

        toolbar.addSeparator()

        self._tb_options = QAction(self._themed_icon("configure"), "Options", self)
        toolbar.addAction(self._tb_options)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _build_central_widget(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Session tabs (multi-tab workspace)
        self._session_tabs = QTabBar(central)
        self._session_tabs.setExpanding(False)
        self._session_tabs.setDrawBase(True)
        self._session_tabs.setMovable(False)
        self._session_tabs.setTabsClosable(False)
        layout.addWidget(self._session_tabs)

        # Path bar
        self._path_bar = PathBar(central)
        layout.addWidget(self._path_bar)

        # View-switcher tab bar
        self._view_switcher = QTabBar(central)
        self._view_switcher.addTab("Folder Compare")
        self._view_switcher.addTab("Text Compare")
        self._view_switcher.addTab("Hex Compare")
        self._view_switcher.addTab("Image Compare")
        self._view_switcher.setTabsClosable(True)
        for i in range(_BASE_VIEW_TAB_COUNT):
            self._view_switcher.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
            self._view_switcher.setTabButton(i, QTabBar.ButtonPosition.LeftSide, None)
        layout.addWidget(self._view_switcher)

        # Filter bar
        self._filter_bar = FilterBar(central)
        layout.addWidget(self._filter_bar)

        # Stacked widget holding the four comparison views
        self._view_stack = QStackedWidget(central)

        self._folder_view = FolderView(self._view_stack)
        self._view_stack.addWidget(self._folder_view)  # index 0

        self._text_view = TextView(self._view_stack)
        self._view_stack.addWidget(self._text_view)    # index 1

        self._hex_view = HexView(self._view_stack)
        self._view_stack.addWidget(self._hex_view)      # index 2

        self._image_view = ImageView(self._view_stack)
        self._view_stack.addWidget(self._image_view)    # index 3

        layout.addWidget(self._view_stack, 1)  # stretch factor 1

        self.setCentralWidget(central)

        # Initialize first session tab.
        self._sessions = [SessionState(name="Session 1")]
        self._session_tabs.addTab("Session 1")
        self._session_tabs.setCurrentIndex(0)
        self._active_session_index = 0

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self) -> None:
        status_bar: QStatusBar = self.statusBar()
        self._status_summary = QLabel("Ready")
        status_bar.addPermanentWidget(self._status_summary)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # PathBar -> store paths
        self._path_bar.left_path_changed.connect(self._on_left_path_changed)
        self._path_bar.right_path_changed.connect(self._on_right_path_changed)
        self._path_bar.base_path_changed.connect(self._on_base_path_changed)
        self._session_tabs.currentChanged.connect(self._on_session_changed)

        # FilterBar -> FolderView
        self._filter_bar.filters_changed.connect(self._on_filters_changed)
        self._filter_bar.diff_option_changed.connect(self._on_diff_option_changed)

        # File menu
        self._act_new_tab.triggered.connect(self._on_new_session)
        self._act_close_tab.triggered.connect(self._on_close_tab)
        self._act_quit.triggered.connect(self.close)

        # Edit menu
        self._act_copy_lr.triggered.connect(self._on_copy_lr)
        self._act_copy_rl.triggered.connect(self._on_copy_rl)
        self._act_swap_sides.triggered.connect(self._on_swap_sides)
        self._act_find.triggered.connect(self._on_find)
        self._act_find_next.triggered.connect(self._on_find_next)
        self._act_find_prev.triggered.connect(self._on_find_prev)

        # View menu
        self._act_refresh.triggered.connect(self._on_refresh)
        self._act_expand_all.triggered.connect(self._folder_view.expand_all)
        self._act_collapse_all.triggered.connect(self._folder_view.collapse_all)

        # Tools menu
        self._act_compare_now.triggered.connect(self._on_compare)
        self._act_sync.triggered.connect(self._on_sync)
        self._act_profiles.triggered.connect(self._on_profiles)

        # Settings menu
        self._act_configure_shortcuts.triggered.connect(self._on_configure_shortcuts)
        self._act_configure_toolbars.triggered.connect(self._on_configure_toolbars)
        self._act_preferences.triggered.connect(self._on_preferences)

        # Help menu
        self._act_handbook.triggered.connect(self._on_handbook)
        self._act_report_bug.triggered.connect(self._on_report_bug)
        self._act_about.triggered.connect(self._on_about)
        self._act_about_kde.triggered.connect(self._on_about_kde)

        # Toolbar actions (keep existing toolbar)
        self._tb_compare.triggered.connect(self._on_compare)
        self._tb_cancel.triggered.connect(self._on_cancel)
        self._tb_refresh.triggered.connect(self._on_refresh)
        self._tb_new.triggered.connect(self._on_new_session)
        self._tb_home.triggered.connect(self._on_home)
        self._tb_swap.triggered.connect(self._on_swap_sides)
        self._tb_expand_all.triggered.connect(self._folder_view.expand_all)
        self._tb_collapse_all.triggered.connect(self._folder_view.collapse_all)
        self._tb_copy_lr.triggered.connect(self._on_copy_lr)
        self._tb_copy_rl.triggered.connect(self._on_copy_rl)
        self._tb_sync.triggered.connect(self._on_sync)
        self._tb_options.triggered.connect(self._on_preferences)
        self._tb_profiles.triggered.connect(self._on_profiles)

        # FolderView file activated -> detect type and switch view
        self._folder_view.file_activated.connect(self._on_file_activated)
        self._folder_view.context_command.connect(self._on_folder_context_command)

        # View switcher tab bar <-> stacked widget
        self._view_switcher.currentChanged.connect(self._on_view_tab_changed)
        self._view_switcher.tabCloseRequested.connect(self._on_view_tab_close_requested)

        # View menu radio actions -> switch view
        self._act_view_folder.triggered.connect(lambda: self._switch_view(0))
        self._act_view_text.triggered.connect(lambda: self._switch_view(1))
        self._act_view_hex.triggered.connect(lambda: self._switch_view(2))
        self._act_view_image.triggered.connect(lambda: self._switch_view(3))

        # View menu filter checkboxes
        self._act_show_identical.toggled.connect(self._on_view_filter_toggled)
        self._act_show_different.toggled.connect(self._on_view_filter_toggled)
        self._act_show_left_only.toggled.connect(self._on_view_filter_toggled)
        self._act_show_right_only.toggled.connect(self._on_view_filter_toggled)
        self._act_show_files_only.toggled.connect(self._on_view_filter_toggled)
        self._act_filter_all.triggered.connect(lambda: self._apply_quick_filter_preset("all"))
        self._act_filter_diffs.triggered.connect(lambda: self._apply_quick_filter_preset("diffs"))
        self._act_filter_same.triggered.connect(lambda: self._apply_quick_filter_preset("same"))
        self._tb_filter_all.triggered.connect(lambda: self._apply_quick_filter_preset("all"))
        self._tb_filter_diffs.triggered.connect(lambda: self._apply_quick_filter_preset("diffs"))
        self._tb_filter_same.triggered.connect(lambda: self._apply_quick_filter_preset("same"))
        self._act_always_show_folders.toggled.connect(self._on_folder_view_options_changed)
        self._act_mode_compare_structure.triggered.connect(self._on_folder_view_options_changed)
        self._act_mode_files_only.triggered.connect(self._on_folder_view_options_changed)
        self._act_mode_ignore_structure.triggered.connect(self._on_folder_view_options_changed)

        # 3-Way toggle
        self._tb_three_way.toggled.connect(self._on_three_way_toggled)

    # ------------------------------------------------------------------
    # Show event -- deferred CLI error dialog
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._deferred_cli_error is not None:
            msg = self._deferred_cli_error
            self._deferred_cli_error = None
            QMessageBox.warning(
                self,
                "CLI Not Found",
                f"{msg}\n\nYou can set the path in Tools > Options.",
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
        self._session_tabs.setTabText(idx, title)

    def _capture_session_state(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._sessions):
            return
        session = self._sessions[idx]
        session.left_path = self._left_path
        session.right_path = self._right_path
        session.base_path = self._base_path
        session.settings = ComparisonSettings(
            ignore_patterns=list(self._settings.ignore_patterns),
            follow_symlinks=self._settings.follow_symlinks,
            use_hash_verification=self._settings.use_hash_verification,
            cache_dir=self._settings.cache_dir,
        )
        session.three_way_mode = self._three_way_mode
        session.show_identical = self._filter_bar.show_identical
        session.show_different = self._filter_bar.show_different
        session.show_left_only = self._filter_bar.show_left_only
        session.show_right_only = self._filter_bar.show_right_only
        session.show_files_only = self._filter_bar.show_files_only
        session.search_text = self._filter_bar.search_text
        session.diff_option_mode = self._filter_bar.diff_option_mode
        session.active_view = self._view_stack.currentIndex()
        session.report = self._current_report
        session.status_summary = self._status_summary.text() or "Ready"
        session.folder_view_mode = self._folder_view_mode()
        session.always_show_folders = self._act_always_show_folders.isChecked()
        self._update_active_session_title()

    def _apply_session_state(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._sessions):
            return

        session = self._sessions[idx]
        self._active_session_index = idx
        self._settings = ComparisonSettings(
            ignore_patterns=list(session.settings.ignore_patterns),
            follow_symlinks=session.settings.follow_symlinks,
            use_hash_verification=session.settings.use_hash_verification,
            cache_dir=session.settings.cache_dir,
        )

        self._path_bar.left_path = session.left_path
        self._path_bar.right_path = session.right_path
        self._path_bar.base_path = session.base_path
        self._left_path = session.left_path
        self._right_path = session.right_path
        self._base_path = session.base_path

        self._three_way_mode = session.three_way_mode
        self._tb_three_way.blockSignals(True)
        self._tb_three_way.setChecked(session.three_way_mode)
        self._tb_three_way.blockSignals(False)
        self._path_bar.set_three_way_mode(session.three_way_mode)

        self._filter_bar.blockSignals(True)
        self._filter_bar.show_identical = session.show_identical
        self._filter_bar.show_different = session.show_different
        self._filter_bar.show_left_only = session.show_left_only
        self._filter_bar.show_right_only = session.show_right_only
        self._filter_bar.show_files_only = session.show_files_only
        self._filter_bar.search_text = session.search_text
        self._filter_bar.diff_option_mode = session.diff_option_mode
        self._filter_bar.blockSignals(False)

        self._act_show_identical.setChecked(session.show_identical)
        self._act_show_different.setChecked(session.show_different)
        self._act_show_left_only.setChecked(session.show_left_only)
        self._act_show_right_only.setChecked(session.show_right_only)
        self._act_show_files_only.setChecked(session.show_files_only)
        self._folder_view.set_filters(
            session.show_identical,
            session.show_different,
            session.show_left_only,
            session.show_right_only,
            session.show_files_only,
            session.search_text,
            session.diff_option_mode,
        )

        self._switch_view(session.active_view if 0 <= session.active_view <= 3 else 0)

        self._current_report = session.report
        self._set_folder_view_options(session.folder_view_mode, session.always_show_folders)
        if session.report is not None:
            self._rebuild_folder_tree_from_report()
        else:
            self._folder_view.set_tree(
                TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
            )

        self._status_summary.setText(session.status_summary or "Ready")
        self._tb_cancel.setEnabled(False)
        self._tb_compare.setEnabled(True)
        self.statusBar().clearMessage()
        self._update_quick_filter_actions()
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
    # Path slots
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_left_path_changed(self, path: str) -> None:
        self._left_path = path
        session = self._current_session()
        session.left_path = path
        self._update_active_session_title()

    @Slot(str)
    def _on_right_path_changed(self, path: str) -> None:
        self._right_path = path
        session = self._current_session()
        session.right_path = path
        self._update_active_session_title()

    @Slot(str)
    def _on_base_path_changed(self, path: str) -> None:
        self._base_path = path
        session = self._current_session()
        session.base_path = path

    # ------------------------------------------------------------------
    # Filter slots
    # ------------------------------------------------------------------

    @Slot(bool, bool, bool, bool, bool, str)
    def _on_filters_changed(
        self,
        show_identical: bool,
        show_different: bool,
        show_left_only: bool,
        show_right_only: bool,
        show_files_only: bool,
        search_text: str,
    ) -> None:
        self._folder_view.set_filters(
            show_identical,
            show_different,
            show_left_only,
            show_right_only,
            show_files_only,
            search_text,
            self._filter_bar.diff_option_mode,
        )
        # Keep View menu checkboxes in sync with the active filter bar state.
        self._act_show_identical.setChecked(show_identical)
        self._act_show_different.setChecked(show_different)
        self._act_show_left_only.setChecked(show_left_only)
        self._act_show_right_only.setChecked(show_right_only)
        self._act_show_files_only.setChecked(show_files_only)
        session = self._current_session()
        session.show_identical = show_identical
        session.show_different = show_different
        session.show_left_only = show_left_only
        session.show_right_only = show_right_only
        session.show_files_only = show_files_only
        session.search_text = search_text
        session.diff_option_mode = self._filter_bar.diff_option_mode
        self._update_quick_filter_actions()

    @Slot(str)
    def _on_diff_option_changed(self, mode: str) -> None:
        self._folder_view.set_diff_option_mode(mode)
        self._current_session().diff_option_mode = mode

    @Slot()
    def _on_view_filter_toggled(self) -> None:
        """Sync the View menu filter checkboxes into the FilterBar."""
        self._filter_bar.show_identical = self._act_show_identical.isChecked()
        self._filter_bar.show_different = self._act_show_different.isChecked()
        self._filter_bar.show_left_only = self._act_show_left_only.isChecked()
        self._filter_bar.show_right_only = self._act_show_right_only.isChecked()
        self._filter_bar.show_files_only = self._act_show_files_only.isChecked()
        self._update_quick_filter_actions()

    def _apply_quick_filter_preset(self, preset: str) -> None:
        if preset == "all":
            self._act_show_identical.setChecked(True)
            self._act_show_different.setChecked(True)
            self._act_show_left_only.setChecked(True)
            self._act_show_right_only.setChecked(True)
        elif preset == "diffs":
            self._act_show_identical.setChecked(False)
            self._act_show_different.setChecked(True)
            self._act_show_left_only.setChecked(True)
            self._act_show_right_only.setChecked(True)
        elif preset == "same":
            self._act_show_identical.setChecked(True)
            self._act_show_different.setChecked(False)
            self._act_show_left_only.setChecked(False)
            self._act_show_right_only.setChecked(False)
        self._act_show_files_only.setChecked(self._filter_bar.show_files_only)
        self._on_view_filter_toggled()

    def _update_quick_filter_actions(self) -> None:
        identical = self._filter_bar.show_identical
        different = self._filter_bar.show_different
        left_only = self._filter_bar.show_left_only
        right_only = self._filter_bar.show_right_only

        all_match = identical and different and left_only and right_only
        diffs_match = (not identical) and different and left_only and right_only
        same_match = identical and (not different) and (not left_only) and (not right_only)

        actions = [
            self._act_filter_all,
            self._act_filter_diffs,
            self._act_filter_same,
            self._tb_filter_all,
            self._tb_filter_diffs,
            self._tb_filter_same,
        ]
        for action in actions:
            action.blockSignals(True)
        self._act_filter_all.setChecked(all_match)
        self._tb_filter_all.setChecked(all_match)
        self._act_filter_diffs.setChecked(diffs_match)
        self._tb_filter_diffs.setChecked(diffs_match)
        self._act_filter_same.setChecked(same_match)
        self._tb_filter_same.setChecked(same_match)
        for action in actions:
            action.blockSignals(False)

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

        self._worker = ComparisonWorker(self._cli_bridge, self)
        self._worker.finished.connect(self._on_comparison_finished)
        self._worker.error.connect(self._on_comparison_error)
        self._worker.progress.connect(self._on_comparison_progress)

        self._tb_cancel.setEnabled(True)
        self._tb_compare.setEnabled(False)
        self._status_summary.setText("Comparing...")
        self._current_session().status_summary = "Comparing..."
        self.statusBar().showMessage("Starting comparison...")

        self._worker.start_scan(
            left=left,
            right=right,
            follow_symlinks=self._settings.follow_symlinks,
            verify_hashes=self._settings.use_hash_verification,
            ignore_patterns=self._settings.ignore_patterns or None,
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
        self._tb_cancel.setEnabled(False)
        self._tb_compare.setEnabled(True)
        self._status_summary.setText("Cancelled")
        self._current_session().status_summary = "Cancelled"
        self.statusBar().showMessage("Comparison cancelled.", 5000)

    @Slot(object)
    def _on_comparison_finished(self, report: ScanReport) -> None:
        """Handle a completed comparison."""
        self._current_report = report
        session = self._current_session()
        session.report = report
        self._tb_cancel.setEnabled(False)
        self._tb_compare.setEnabled(True)

        self._rebuild_folder_tree_from_report()

        summary = report.summary
        status_text = (
            f"{summary.same} identical, "
            f"{summary.different} different, "
            f"{summary.orphan_left} left only, "
            f"{summary.orphan_right} right only"
        )
        session.status_summary = status_text
        self._status_summary.setText(status_text)
        self.statusBar().showMessage("Comparison complete.", 5000)
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
        self._tb_cancel.setEnabled(False)
        self._tb_compare.setEnabled(True)
        self._status_summary.setText("Error")
        self._current_session().status_summary = "Error"
        log_error("compare failed", error_text=message)
        QMessageBox.critical(self, "Comparison Error", message)

    @Slot(str)
    def _on_comparison_progress(self, message: str) -> None:
        """Show progress messages in the status bar."""
        self.statusBar().showMessage(message)

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
        home = str(Path.home())
        self._path_bar.left_path = home
        self._path_bar.right_path = home
        self.statusBar().showMessage(f"Set both sides to home: {home}", 5000)

    @Slot()
    def _on_swap_sides(self) -> None:
        left = self._path_bar.left_path
        right = self._path_bar.right_path
        self._path_bar.left_path = right
        self._path_bar.right_path = left
        self.statusBar().showMessage("Swapped left/right sides.", 5000)

    @Slot()
    def _on_focus_filter_search(self) -> None:
        self._filter_bar.focus_search()

    @Slot()
    def _on_clear_filter_search(self) -> None:
        self._filter_bar.clear_search()

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
        self._session_tabs.addTab(session.name)
        self._session_tabs.setCurrentIndex(new_index)

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_view_tab_changed(self, index: int) -> None:
        """Synchronise the stacked widget and radio actions with the tab bar."""
        if index < 0 or index >= self._view_stack.count():
            return
        self._view_stack.setCurrentIndex(index)
        actions = [
            self._act_view_folder,
            self._act_view_text,
            self._act_view_hex,
            self._act_view_image,
        ]
        if 0 <= index < len(actions):
            actions[index].setChecked(True)
        self._current_session().active_view = index

    def _switch_view(self, index: int) -> None:
        """Programmatically switch the current view."""
        if index < 0 or index >= self._view_stack.count():
            return
        self._view_stack.setCurrentIndex(index)
        self._view_switcher.setCurrentIndex(index)

    @Slot(int)
    def _on_view_tab_close_requested(self, index: int) -> None:
        """Close dynamic file-compare tabs while keeping base view tabs intact."""
        if index < _BASE_VIEW_TAB_COUNT:
            return
        if index < 0 or index >= self._view_stack.count():
            return

        widget = self._view_stack.widget(index)
        self._view_stack.removeWidget(widget)
        self._view_switcher.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        self._reindex_file_compare_tabs()

        next_index = min(index, self._view_stack.count() - 1)
        if next_index >= 0:
            self._switch_view(next_index)

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
        if mode == "text":
            view = TextView(self._view_stack)
            view.compare_files(str(left_file), str(right_file))
            widget = view
            label = f"Text: {Path(path).name}"
        elif mode == "image":
            view = ImageView(self._view_stack)
            view.compare_images(str(left_file), str(right_file))
            widget = view
            label = f"Image: {Path(path).name}"
        else:
            view = HexView(self._view_stack)
            view.compare_files(str(left_file), str(right_file))
            widget = view
            label = f"Hex: {Path(path).name}"

        index = self._view_stack.addWidget(widget)
        self._view_switcher.addTab(label)
        self._view_switcher.setTabData(index, tab_key)
        self._file_compare_tabs[tab_key] = index
        self._switch_view(index)
        log_info("file compare tab opened", rel_path=path, mode=mode, index=index)

    def _determine_file_compare_mode(self, rel_path: str) -> str:
        suffix = Path(rel_path).suffix.lower()
        if suffix in TEXT_EXTENSIONS:
            return "text"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        return "hex"

    def _resolve_compare_file_paths(self, rel_path: str) -> Optional[tuple[Path, Path]]:
        left_root = Path(self._left_path)
        right_root = Path(self._right_path)
        if not left_root.exists() or not right_root.exists():
            return None

        rel = Path(rel_path)
        left_file = left_root / rel
        right_file = right_root / rel
        if not left_file.exists() or not right_file.exists():
            return None
        if left_file.is_dir() or right_file.is_dir():
            return None
        return left_file, right_file

    def _make_file_tab_key(self, mode: str, left_file: Path, right_file: Path) -> str:
        return f"{mode}|{left_file.resolve()}|{right_file.resolve()}"

    def _reindex_file_compare_tabs(self) -> None:
        self._file_compare_tabs.clear()
        for index in range(_BASE_VIEW_TAB_COUNT, self._view_switcher.count()):
            key = self._view_switcher.tabData(index)
            if isinstance(key, str) and key:
                self._file_compare_tabs[key] = index

    # ------------------------------------------------------------------
    # 3-Way toggle
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_three_way_toggled(self, checked: bool) -> None:
        self._three_way_mode = checked
        self._path_bar.set_three_way_mode(checked)
        self._current_session().three_way_mode = checked

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
            QMessageBox.information(
                self,
                "Align With",
                "Alignment helpers are not implemented yet.",
            )
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

        if self._cli_bridge is not None:
            direction = "left_to_right" if left_to_right else "right_to_left"
            try:
                report = self._cli_bridge.copy_paths(
                    left=self._left_path,
                    right=self._right_path,
                    direction=direction,
                    paths=rel_paths,
                    dry_run=False,
                )
                summary = report.get("summary", {})
                copied = int(summary.get("copied", 0))
                missing = int(summary.get("missing", 0))
                skipped = int(summary.get("skipped", 0))
                failed = int(summary.get("failed", 0))
                label = "Left -> Right" if left_to_right else "Right -> Left"
                self.statusBar().showMessage(
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
                return
            except Exception as exc:
                log_warning("copy via cli failed; fallback to local", error=str(exc))
                self.statusBar().showMessage(
                    f"CLI copy failed, using local fallback: {exc}",
                    7000,
                )

        copied = 0
        missing = 0
        failed = 0

        for rel_path in rel_paths:
            rel = Path(rel_path)
            source = left_root / rel if left_to_right else right_root / rel
            target = right_root / rel if left_to_right else left_root / rel

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
        self.statusBar().showMessage(
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
            try:
                report = self._cli_bridge.sync_folders(
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
                summary = report.get("summary", {})
                copied = int(summary.get("copied", 0))
                updated = int(summary.get("updated", 0))
                deleted = int(summary.get("deleted", 0))
                skipped = int(summary.get("skipped", 0))
                failed = int(summary.get("failed", 0))
                label = "Sync dry-run" if dry_run else "Sync complete"
                self.statusBar().showMessage(
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
                return
            except Exception as exc:
                log_warning("sync via cli failed; fallback to local", error=str(exc))
                self.statusBar().showMessage(
                    f"CLI sync failed, using local fallback: {exc}",
                    7000,
                )

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
            self.statusBar().showMessage("No synchronization actions required.", 5000)
            return

        if dry_run:
            copy_count = sum(1 for code, _ in actions if code in {"COPY_LR", "COPY_RL"})
            update_count = sum(1 for code, _ in actions if code in {"UPDATE_L", "UPDATE_R"})
            delete_count = sum(1 for code, _ in actions if code in {"DELETE_L", "DELETE_R"})
            skipped = sum(1 for code, _ in actions if code in {"SKIP", "CONFLICT"})
            self.statusBar().showMessage(
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
            rel = Path(rel_path)
            left_path = left_root / rel
            right_path = right_root / rel

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

        self.statusBar().showMessage(
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
        rel = Path(rel_path)

        preferred = left_root / rel if side == "left" else right_root / rel
        fallback = right_root / rel if side == "left" else left_root / rel

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
        rel = Path(rel_path)
        primary = self._side_root(side) / rel
        if primary.exists():
            return primary
        if allow_fallback:
            secondary = self._side_root(self._other_side(side)) / rel
            if secondary.exists():
                return secondary
        return None

    def _set_base_folder_from_side(self, rel_path: str, side: str, *, other_side: bool) -> None:
        effective_side = self._other_side(side) if other_side else side
        base = self._side_root(effective_side) / Path(rel_path)
        if base.exists() and base.is_file():
            base = base.parent
        elif not base.exists():
            base = base.parent
        if not base.exists():
            base = self._side_root(effective_side)

        self._base_path = str(base)
        self._path_bar.base_path = self._base_path
        self._current_session().base_path = self._base_path
        self.statusBar().showMessage(f"Base folder set to: {base}", 6000)

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
            self.statusBar().showMessage(f"Copied to: {target}", 7000)
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
            self.statusBar().showMessage(f"Moved to: {target}", 7000)
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
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            self.statusBar().showMessage(f"Deleted: {target}", 7000)
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
            self.statusBar().showMessage(f"Renamed to: {renamed.name}", 7000)
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

        try:
            os.utime(target, None)
            self.statusBar().showMessage(f"Touched: {target.name}", 5000)
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
            self.statusBar().showMessage(f"Excluded: {rel}", 6000)
            self._on_refresh()

    def _toggle_ignored(self, rel_path: str) -> None:
        rel = rel_path.strip()
        if not rel:
            return
        patterns = list(self._settings.ignore_patterns)
        if rel in patterns:
            patterns = [p for p in patterns if p != rel]
            self.statusBar().showMessage(f"Removed from ignored: {rel}", 6000)
        else:
            patterns.append(rel)
            self.statusBar().showMessage(f"Added to ignored: {rel}", 6000)
        self._settings.ignore_patterns = patterns
        self._current_session().settings.ignore_patterns = list(patterns)
        self._on_refresh()

    def _create_new_folder(self, rel_path: str, side: str) -> None:
        base = self._side_root(side) / Path(rel_path)
        if base.exists() and base.is_file():
            base = base.parent
        elif not base.exists():
            base = base.parent
        base.mkdir(parents=True, exist_ok=True)

        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return

        target = base / name
        try:
            target.mkdir(parents=True, exist_ok=False)
            self.statusBar().showMessage(f"Created folder: {target}", 6000)
            self._on_refresh()
        except FileExistsError:
            QMessageBox.warning(self, "New Folder", f"Folder already exists:\n{target}")
        except OSError as exc:
            QMessageBox.critical(self, "New Folder Failed", str(exc))

    def _copy_filename(self, rel_path: str) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(Path(rel_path).name)
        self.statusBar().showMessage("Filename copied to clipboard.", 4000)

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
    def _on_options(self) -> None:
        """Open the Settings dialog and apply changes on accept."""
        dialog = SettingsDialog(self._config, self._settings, self)
        if dialog.exec():
            # Re-read settings that may have changed
            self._settings = dialog.get_settings()
            self._current_session().settings = ComparisonSettings(
                ignore_patterns=list(self._settings.ignore_patterns),
                follow_symlinks=self._settings.follow_symlinks,
                use_hash_verification=self._settings.use_hash_verification,
                cache_dir=self._settings.cache_dir,
            )
            updates = dialog.get_config_updates()
            self._config.theme = str(updates.get("theme", self._config.theme))
            self._config.cli_path = updates.get("cli_path")
            # Update CLI bridge if path changed
            try:
                cli_path = self._config.get_cli_path()
                self._cli_bridge = CliBridge(cli_path)
            except FileNotFoundError:
                self._cli_bridge = None
            self._sync_config_from_runtime()
            self._config.save()

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
        self._profile_manager.add(profile)
        self.statusBar().showMessage(f"Profile '{profile.name}' saved.", 5000)
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
            self._profile_manager.add(profile)
            return

        existing.left_path = self._left_path
        existing.right_path = self._right_path
        existing.base_path = self._base_path
        existing.ignore_patterns = list(self._settings.ignore_patterns)
        existing.follow_symlinks = self._settings.follow_symlinks
        existing.hash_verification = self._settings.use_hash_verification
        existing.last_used = now
        self._profile_manager.update(existing)

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
                self.statusBar().showMessage(
                    f"Profile '{profile.name}' loaded.", 5000,
                )
                log_info("profile loaded", name=profile.name)

    @Slot()
    def _on_about(self) -> None:
        """Open the About dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    @Slot()
    def _on_close_tab(self) -> None:
        """Close the current session tab."""
        if len(self._sessions) <= 1:
            # Don't close the last tab
            return

        current = self._session_tabs.currentIndex()
        if current >= _BASE_VIEW_TAB_COUNT:
            # Close session tab
            self._session_tabs.removeTab(current)
            del self._sessions[current - _BASE_VIEW_TAB_COUNT]
            if self._active_session_index >= current - _BASE_VIEW_TAB_COUNT:
                self._active_session_index = max(0, self._active_session_index - 1)
        # Note: Can't close base view tabs (Folder/Text/Hex/Image)

    @Slot()
    def _on_find(self) -> None:
        """Focus the filter/search field."""
        self._filter_bar.focus_search()

    @Slot()
    def _on_find_next(self) -> None:
        """Find next occurrence (placeholder)."""
        # TODO: Implement find next when search supports it
        pass

    @Slot()
    def _on_find_prev(self) -> None:
        """Find previous occurrence (placeholder)."""
        # TODO: Implement find previous when search supports it
        pass

    @Slot()
    def _on_profiles(self) -> None:
        """Open the Profiles dialog."""
        dialog = ProfilesDialog(self._profile_manager, self)
        if dialog.exec():
            selected = dialog.selected_profile()
            if selected:
                self._apply_profile(selected)

    @Slot()
    def _on_preferences(self) -> None:
        """Open the Settings/Preferences dialog."""
        dialog = SettingsDialog(self._config, self._settings, self)
        if dialog.exec():
            self._settings = dialog.get_settings()
            self._current_session().settings = ComparisonSettings(
                ignore_patterns=list(self._settings.ignore_patterns),
                follow_symlinks=self._settings.follow_symlinks,
                use_hash_verification=self._settings.use_hash_verification,
                cache_dir=self._settings.cache_dir,
            )

    @Slot()
    def _on_configure_shortcuts(self) -> None:
        """Open Configure Shortcuts dialog (placeholder)."""
        QMessageBox.information(
            self,
            "Configure Shortcuts",
            "Keyboard shortcut configuration will be available in a future release.",
        )

    @Slot()
    def _on_configure_toolbars(self) -> None:
        """Open Configure Toolbars dialog (placeholder)."""
        QMessageBox.information(
            self,
            "Configure Toolbars",
            "Toolbar customization will be available in a future release.",
        )

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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Save window geometry to config before closing."""
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
            if self._session_tabs.count() == 0:
                self._session_tabs.addTab("Session 1")
                self._session_tabs.setCurrentIndex(0)
            self._active_session_index = 0

        session = self._sessions[0]
        settings = self._config.comparison_settings or {}
        raw_patterns = settings.get("ignore_patterns", [])
        ignore_patterns = raw_patterns if isinstance(raw_patterns, list) else []
        session.settings = ComparisonSettings(
            ignore_patterns=[str(p) for p in ignore_patterns if isinstance(p, str)],
            follow_symlinks=bool(settings.get("follow_symlinks", False)),
            use_hash_verification=bool(settings.get("use_hash_verification", True)),
            cache_dir=settings.get("cache_dir")
            if isinstance(settings.get("cache_dir"), str)
            else None,
        )

        paths = self._config.last_paths or {}
        session.left_path = str(paths.get("left", ""))
        session.right_path = str(paths.get("right", ""))
        session.base_path = str(paths.get("base", ""))

        session.three_way_mode = bool(self._config.three_way_mode)

        filters = self._config.filter_options or {}
        session.show_identical = bool(filters.get("show_identical", True))
        session.show_different = bool(filters.get("show_different", True))
        session.show_left_only = bool(filters.get("show_left_only", True))
        session.show_right_only = bool(filters.get("show_right_only", True))
        session.show_files_only = bool(filters.get("show_files_only", False))
        session.search_text = str(filters.get("search_text", ""))
        mode_value = filters.get("diff_option_mode", "show_differences")
        session.diff_option_mode = (
            str(mode_value) if isinstance(mode_value, str) else "show_differences"
        )
        mode_value = filters.get("folder_view_mode", "compare_structure")
        session.folder_view_mode = (
            str(mode_value) if isinstance(mode_value, str) else "compare_structure"
        )
        session.always_show_folders = bool(filters.get("always_show_folders", True))
        session.status_summary = "Ready"
        session.report = None

        view_index = self._config.active_view
        session.active_view = view_index if isinstance(view_index, int) else 0
        if session.active_view < 0 or session.active_view > 3:
            session.active_view = 0

        self._session_tabs.setCurrentIndex(0)
        self._apply_session_state(0)
        self._folder_view.set_column_widths(self._config.folder_columns or {})

    def _sync_config_from_runtime(self) -> None:
        """Write current runtime state into AppConfig before save."""
        self._config.comparison_settings = {
            "ignore_patterns": list(self._settings.ignore_patterns),
            "follow_symlinks": self._settings.follow_symlinks,
            "use_hash_verification": self._settings.use_hash_verification,
            "cache_dir": self._settings.cache_dir,
        }
        self._config.filter_options = {
            "show_identical": self._filter_bar.show_identical,
            "show_different": self._filter_bar.show_different,
            "show_left_only": self._filter_bar.show_left_only,
            "show_right_only": self._filter_bar.show_right_only,
            "show_files_only": self._filter_bar.show_files_only,
            "search_text": self._filter_bar.search_text,
            "diff_option_mode": self._filter_bar.diff_option_mode,
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
