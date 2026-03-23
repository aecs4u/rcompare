"""Main application window -- central orchestrator for the RCompare PySide6 frontend."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
from typing import Optional

from PySide6.QtCore import Qt, QMimeData, QUrl, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QProgressBar,
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
from .views.home_view import HomeView
from .widgets.filter_bar import FilterBar
from .widgets.color_legend import ColorLegend
from .workers.comparison_worker import ComparisonWorker
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
_BASE_VIEW_TAB_COUNT = 6  # Home + Folder + Text + Hex + Image + Table


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
        self._undo_history: OperationHistory = OperationHistory()
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
        self.setAcceptDrops(True)

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
        self._act_quit.setShortcut(QKeySequence.StandardKey.Quit)  # Ctrl+Q
        file_menu.addAction(self._act_quit)

        # -- Edit -------------------------------------------------------
        edit_menu = menu_bar.addMenu("&Edit")

        self._act_undo = QAction(self._themed_icon("edit-undo"), "&Undo", self)
        self._act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._act_undo.setEnabled(False)
        edit_menu.addAction(self._act_undo)

        self._act_redo = QAction(self._themed_icon("edit-redo"), "&Redo", self)
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

        # Difference navigation
        self._tb_prev_diff = QAction(self._themed_icon("go-up-skip", "go-up"), "Prev Diff", self)
        self._tb_prev_diff.setToolTip("Previous Difference (Alt+Up)")
        toolbar.addAction(self._tb_prev_diff)

        self._tb_next_diff = QAction(self._themed_icon("go-down-skip", "go-down"), "Next Diff", self)
        self._tb_next_diff.setToolTip("Next Difference (Alt+Down)")
        toolbar.addAction(self._tb_next_diff)

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

        self._tb_apply = QAction(
            self._themed_icon("dialog-ok-apply", "dialog-ok"), "Apply", self
        )
        self._tb_apply.setToolTip("Apply selected difference (Ctrl+Return)")
        toolbar.addAction(self._tb_apply)

        toolbar.addSeparator()

        self._tb_save_diff = QAction(self._themed_icon("document-save"), "Save Diff", self)
        self._tb_save_diff.setToolTip("Save comparison as diff file")
        toolbar.addAction(self._tb_save_diff)

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
        self._view_switcher.addTab("Home")
        self._view_switcher.addTab("Folder Compare")
        self._view_switcher.addTab("Text Compare")
        self._view_switcher.addTab("Hex Compare")
        self._view_switcher.addTab("Image Compare")
        self._view_switcher.addTab("Table Compare")
        self._view_switcher.setTabsClosable(True)
        for i in range(_BASE_VIEW_TAB_COUNT):
            self._view_switcher.setTabButton(i, QTabBar.ButtonPosition.RightSide, None)
            self._view_switcher.setTabButton(i, QTabBar.ButtonPosition.LeftSide, None)
        layout.addWidget(self._view_switcher)

        # Filter bar
        self._filter_bar = FilterBar(central)
        layout.addWidget(self._filter_bar)

        # Color legend
        self._color_legend = ColorLegend(central)
        layout.addWidget(self._color_legend)

        # Stacked widget holding the views
        self._view_stack = QStackedWidget(central)

        # Home view (index 0) - shown on startup
        self._home_view = HomeView(self._config, self._view_stack)
        self._view_stack.addWidget(self._home_view)    # index 0

        self._folder_view = FolderView(self._view_stack)
        self._view_stack.addWidget(self._folder_view)  # index 1

        self._text_view = TextView(self._view_stack)
        self._view_stack.addWidget(self._text_view)    # index 2
        if self._config.appearance:
            self._text_view.apply_appearance(self._config.appearance)

        self._hex_view = HexView(self._view_stack)
        self._view_stack.addWidget(self._hex_view)      # index 3

        self._image_view = ImageView(self._view_stack)
        self._view_stack.addWidget(self._image_view)    # index 4

        # Table view (lazily imported, index 5)
        try:
            from .views.table_view import TableView
            self._table_view = TableView(self._view_stack)
            self._view_stack.addWidget(self._table_view)  # index 5
        except ImportError:
            self._table_view = None

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

        # Left: general message
        self._status_summary = QLabel("Ready")
        status_bar.addWidget(self._status_summary, 1)

        # Progress bar (hidden until a comparison starts)
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.hide()
        status_bar.addPermanentWidget(self._progress_bar)

        # Stage label
        self._status_stage = QLabel("")
        status_bar.addPermanentWidget(self._status_stage)

        # Center: file navigation indicator
        self._status_files = QLabel("")
        status_bar.addPermanentWidget(self._status_files)

        # Right: difference navigation indicator
        self._status_diffs = QLabel("")
        status_bar.addPermanentWidget(self._status_diffs)

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
        self._tb_prev_diff.triggered.connect(self._on_prev_diff)
        self._tb_next_diff.triggered.connect(self._on_next_diff)
        self._tb_expand_all.triggered.connect(self._folder_view.expand_all)
        self._tb_collapse_all.triggered.connect(self._folder_view.collapse_all)
        self._tb_copy_lr.triggered.connect(self._on_copy_lr)
        self._tb_copy_rl.triggered.connect(self._on_copy_rl)
        self._tb_sync.triggered.connect(self._on_sync)
        self._tb_apply.triggered.connect(self._on_apply_diff)
        self._tb_save_diff.triggered.connect(self._on_save_diff)
        self._tb_options.triggered.connect(self._on_preferences)
        self._tb_profiles.triggered.connect(self._on_profiles)

        # HomeView signals
        self._home_view.session_type_selected.connect(self._on_home_session_type)
        self._home_view.recent_session_selected.connect(self._on_home_recent_session)

        # FolderView file activated -> detect type and switch view
        self._folder_view.file_activated.connect(self._on_file_activated)
        self._folder_view.context_command.connect(self._on_folder_context_command)

        # View switcher tab bar <-> stacked widget
        self._view_switcher.currentChanged.connect(self._on_view_tab_changed)
        self._view_switcher.tabCloseRequested.connect(self._on_view_tab_close_requested)

        # View menu radio actions -> switch view (indices shifted +1 for HomeView at 0)
        self._act_view_folder.triggered.connect(lambda: self._switch_view(1))
        self._act_view_text.triggered.connect(lambda: self._switch_view(2))
        self._act_view_hex.triggered.connect(lambda: self._switch_view(3))
        self._act_view_image.triggered.connect(lambda: self._switch_view(4))
        self._act_view_table.triggered.connect(lambda: self._switch_view(5))

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
        self._act_show_preview.toggled.connect(self._on_preview_toggled)
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

        active = session.active_view
        if active < 0 or active > 5:
            active = 1  # Default to Folder view
        self._switch_view(active)

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
        self._worker.progress_update.connect(self._on_progress_update)

        self._tb_cancel.setEnabled(True)
        self._tb_compare.setEnabled(False)
        self._status_summary.setText("Comparing...")
        self._current_session().status_summary = "Comparing..."
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._status_stage.setText("")
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
        self._progress_bar.hide()
        self._status_stage.setText("")

        self._rebuild_folder_tree_from_report()
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
        session.status_summary = status_text
        self._status_summary.setText(status_text)
        self.statusBar().showMessage("Comparison complete.", 5000)

        # Update navigation counters
        diff_entries = self._get_diff_entries()
        all_entries = self._get_all_file_entries()
        self._status_files.setText(f"{len(all_entries)} files")
        self._status_diffs.setText(f"{len(diff_entries)} differences")
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
        self._progress_bar.hide()
        self._status_stage.setText("")
        self._status_summary.setText("Error")
        self._current_session().status_summary = "Error"
        log_error("compare failed", error_text=message)
        QMessageBox.critical(self, "Comparison Error", message)

    @Slot(str)
    def _on_comparison_progress(self, message: str) -> None:
        """Show progress messages in the status bar."""
        self.statusBar().showMessage(message)

    @Slot(object)
    def _on_progress_update(self, info) -> None:
        """Handle structured progress updates from the CLI."""
        self._progress_bar.setValue(info.percent)
        self._status_stage.setText(info.stage_label)
        if info.entries_total > 0:
            self._status_summary.setText(
                f"{info.stage_label} ({info.entries_done:,}/{info.entries_total:,})"
            )
        else:
            self._status_summary.setText(info.stage_label)

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

    @Slot(int)
    def _on_home_session_type(self, view_index: int) -> None:
        """Handle session type card click from HomeView."""
        # view_index: 0=Folder, 1=Text, 2=Hex, 3=Image -> map to stack index +1
        self._switch_view(view_index + 1)

    @Slot(str, str)
    def _on_home_recent_session(self, left: str, right: str) -> None:
        """Handle recent session click from HomeView."""
        self._path_bar.left_path = left
        self._path_bar.right_path = right
        self._switch_view(1)  # Folder view
        self._on_compare()

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
        # Map tab index (0=Home, 1=Folder, 2=Text, 3=Hex, 4=Image, 5=Table)
        actions = {
            1: self._act_view_folder,
            2: self._act_view_text,
            3: self._act_view_hex,
            4: self._act_view_image,
            5: self._act_view_table,
        }
        if index in actions:
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
        if mode == "table":
            try:
                from .views.table_view import TableView
                view = TableView(self._view_stack)
                suffix = Path(path).suffix.lower()
                if suffix in (".xlsx", ".xls"):
                    view.compare_excel(str(left_file), str(right_file))
                else:
                    view.compare_csv(str(left_file), str(right_file))
                widget = view
                label = f"Table: {Path(path).name}"
            except ImportError:
                # Fallback to text view if table_view not available
                view = TextView(self._view_stack)
                view.compare_files(str(left_file), str(right_file))
                widget = view
                label = f"Text: {Path(path).name}"
        elif mode == "text":
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
        if suffix in TABLE_EXTENSIONS:
            return "table"
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
        if checked and not hasattr(self, "_merge_view"):
            self._add_merge_view()

    def _add_merge_view(self) -> None:
        """Lazily add the 3-way merge view to the view stack."""
        try:
            from .views.merge_view import MergeView
            self._merge_view = MergeView(self._view_stack)
            idx = self._view_stack.addWidget(self._merge_view)
            self._view_switcher.addTab("3-Way Merge")
            # Don't allow closing the merge tab via the close button
            self._view_switcher.setTabButton(
                idx, QTabBar.ButtonPosition.RightSide, None,
            )
            self._view_switcher.setTabButton(
                idx, QTabBar.ButtonPosition.LeftSide, None,
            )
        except ImportError:
            log_warning("merge_view module not available")

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
            # Create backup for undo
            backup = create_backup(target, self._undo_history.backup_dir)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            self._record_file_op("delete", str(target), "", str(backup))
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
                self.statusBar().showMessage(
                    f"Timestamp copied from {self._other_side(side)} side: {target.name}", 5000,
                )
            else:
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
                self.statusBar().showMessage(
                    f"Aligned '{filename}' with '{selected}'", 5000,
                )
                log_info("alignment override", source=rel_path, target=selected, side=side)

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
            # Apply appearance settings
            appearance = dialog.get_appearance_settings()
            self._config.appearance = appearance
            self._apply_appearance(appearance)
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
        """Navigate to the next item in the folder view."""
        wrapped = self._folder_view.select_next_match()
        if wrapped:
            self.statusBar().showMessage("Search wrapped to top.", 3000)

    @Slot()
    def _on_find_prev(self) -> None:
        """Navigate to the previous item in the folder view."""
        wrapped = self._folder_view.select_prev_match()
        if wrapped:
            self.statusBar().showMessage("Search wrapped to bottom.", 3000)

    # ------------------------------------------------------------------
    # Difference navigation
    # ------------------------------------------------------------------

    def _get_diff_entries(self) -> list:
        """Return entries from current report that are not identical."""
        report = self._current_report
        if report is None:
            return []
        return [e for e in report.entries if e.status != DiffStatus.SAME and not (e.left and e.left.is_dir)]

    def _get_all_file_entries(self) -> list:
        """Return all file entries from current report."""
        report = self._current_report
        if report is None:
            return []
        return [e for e in report.entries if not (e.left and e.left.is_dir) or not (e.right and e.right.is_dir)]

    def _navigate_entry(self, entries: list, direction: int) -> None:
        """Navigate to next/prev entry in the given list."""
        if not entries:
            self.statusBar().showMessage("No entries to navigate.", 3000)
            return

        # Get current selection
        selected = self._folder_view.selected_paths()
        current_path = selected[0] if selected else ""

        # Find current index
        paths = [e.path for e in entries]
        try:
            current_idx = paths.index(current_path)
            new_idx = current_idx + direction
        except ValueError:
            new_idx = 0 if direction > 0 else len(entries) - 1

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
        self._status_diffs.setText(f"Diff {index + 1} of {total}")

        # Also update file counter
        report = self._current_report
        if report:
            all_files = self._get_all_file_entries()
            if entry and entry.path:
                try:
                    file_idx = [e.path for e in all_files].index(entry.path)
                    self._status_files.setText(f"File {file_idx + 1} of {len(all_files)}")
                except ValueError:
                    pass

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
            self.statusBar().showMessage("No item selected to apply.", 3000)
            return
        self._copy_paths(selected, left_to_right=True)

    @Slot()
    def _on_unapply_diff(self) -> None:
        """Unapply selected difference: copy right -> left."""
        selected = self._folder_view.selected_paths()
        if not selected:
            self.statusBar().showMessage("No item selected to unapply.", 3000)
            return
        self._copy_paths(selected, left_to_right=False)

    @Slot()
    def _on_apply_all(self) -> None:
        """Apply all differences: copy all different/orphan items left -> right."""
        entries = self._get_diff_entries()
        if not entries:
            self.statusBar().showMessage("No differences to apply.", 3000)
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
            self.statusBar().showMessage("No differences to unapply.", 3000)
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
        self.statusBar().showMessage(f"Opened diff: {path}", 5000)
        log_info("opened diff file", path=path)

    @Slot()
    def _on_compare_files_dialog(self) -> None:
        """Open a dialog to select two files/folders to compare."""
        left = QFileDialog.getExistingDirectory(self, "Select Left Folder")
        if not left:
            return
        right = QFileDialog.getExistingDirectory(self, "Select Right Folder")
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
            self.statusBar().showMessage(f"Diff saved: {path}", 5000)
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
        lines.append(f"# RCompare comparison report")
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
                lines.append(f"diff {td.get('path', '?')}")
                for line in td.get("lines", []):
                    ct = line.get("change_type", "equal")
                    content = line.get("content", "")
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
            appearance = dialog.get_appearance_settings()
            self._config.appearance = appearance
            self._apply_appearance(appearance)
            self._config.save()

    @Slot()
    def _on_configure_shortcuts(self) -> None:
        """Open the Configure Keyboard Shortcuts dialog."""
        from .dialogs.shortcuts_dialog import ShortcutsDialog
        dialog = ShortcutsDialog(self)
        dialog.exec()

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
        if session.active_view < 0 or session.active_view > 5:
            session.active_view = 0  # Home view

        self._session_tabs.setCurrentIndex(0)
        self._apply_session_state(0)
        self._folder_view.set_column_widths(self._config.folder_columns or {})
        self._rebuild_bookmarks_menu()

    def _apply_appearance(self, appearance: dict) -> None:
        """Apply appearance settings to all text views."""
        self._text_view.apply_appearance(appearance)

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
                self.statusBar().showMessage(f"Undone: {op.op_type} on {Path(op.source_path).name}", 5000)
            else:
                self.statusBar().showMessage(f"Cannot undo: no backup available", 5000)
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
        self.statusBar().showMessage(f"Redo: {op.op_type} (re-run the operation manually)", 5000)
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
            self._path_bar.left_path = paths[0]
            self._path_bar.right_path = paths[1]
            self.statusBar().showMessage("Dropped two paths — starting comparison...", 5000)
            self._on_compare()
        elif not self._left_path.strip():
            self._path_bar.left_path = paths[0]
            self.statusBar().showMessage(
                f"Left path set to: {paths[0]}  (drop another for right side)", 5000,
            )
        elif not self._right_path.strip():
            self._path_bar.right_path = paths[0]
            self.statusBar().showMessage("Right path set — starting comparison...", 5000)
            self._on_compare()
        else:
            self._path_bar.left_path = paths[0]
            self.statusBar().showMessage(
                f"Left path updated to: {paths[0]}  (drop another for right side)", 5000,
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
        self.statusBar().showMessage(f"Profile '{profile.name}' loaded.", 5000)
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
        self.statusBar().showMessage(f"Bookmark '{name.strip()}' added.", 5000)

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
        self.statusBar().showMessage(f"Bookmark '{name}' removed.", 5000)

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
                lambda checked=False, l=left, r=right: self._load_bookmark(l, r)
            )
            self._bookmarks_menu.addAction(action)

    def _load_bookmark(self, left: str, right: str) -> None:
        """Load a bookmarked path pair."""
        self._path_bar.left_path = left
        self._path_bar.right_path = right
        self.statusBar().showMessage("Bookmark loaded.", 5000)
        if left and right:
            self._on_compare()
