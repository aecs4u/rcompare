"""Main application window -- central orchestrator for the RCompare PySide6 frontend."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
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
from .models.comparison import build_tree, TreeNode
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


class MainWindow(QMainWindow):
    """Central application window that wires together all views, menus,
    toolbar actions and background workers.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, config: AppConfig) -> None:
        super().__init__()

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

        # --- CLI bridge ------------------------------------------------
        self._cli_bridge: Optional[CliBridge] = None
        try:
            cli_path = config.get_cli_path()
            self._cli_bridge = CliBridge(cli_path)
        except FileNotFoundError as exc:
            # Defer the dialog until after the window is shown so the
            # event loop is running.
            self._deferred_cli_error: Optional[str] = str(exc)
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

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menu_bar(self) -> None:
        menu_bar: QMenuBar = self.menuBar()

        # -- File -------------------------------------------------------
        file_menu = menu_bar.addMenu("&File")

        self._act_new_session = QAction("New Session", self)
        self._act_new_session.setShortcut(QKeySequence("Ctrl+N"))
        file_menu.addAction(self._act_new_session)

        file_menu.addSeparator()

        self._act_exit = QAction("Exit", self)
        self._act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        file_menu.addAction(self._act_exit)

        # -- Edit -------------------------------------------------------
        edit_menu = menu_bar.addMenu("&Edit")

        self._act_copy_lr = QAction("Copy Left to Right", self)
        self._act_copy_lr.setShortcut(QKeySequence(Qt.Key.Key_F7))
        edit_menu.addAction(self._act_copy_lr)

        self._act_copy_rl = QAction("Copy Right to Left", self)
        self._act_copy_rl.setShortcut(QKeySequence(Qt.Key.Key_F8))
        edit_menu.addAction(self._act_copy_rl)

        # -- View -------------------------------------------------------
        view_menu = menu_bar.addMenu("&View")

        compare_submenu = view_menu.addMenu("Compare Mode")
        self._view_action_group = QActionGroup(self)
        self._view_action_group.setExclusive(True)

        self._act_view_folder = QAction("Folder Compare", self)
        self._act_view_folder.setCheckable(True)
        self._act_view_folder.setChecked(True)
        self._view_action_group.addAction(self._act_view_folder)
        compare_submenu.addAction(self._act_view_folder)

        self._act_view_text = QAction("Text Compare", self)
        self._act_view_text.setCheckable(True)
        self._view_action_group.addAction(self._act_view_text)
        compare_submenu.addAction(self._act_view_text)

        self._act_view_hex = QAction("Hex Compare", self)
        self._act_view_hex.setCheckable(True)
        self._view_action_group.addAction(self._act_view_hex)
        compare_submenu.addAction(self._act_view_hex)

        self._act_view_image = QAction("Image Compare", self)
        self._act_view_image.setCheckable(True)
        self._view_action_group.addAction(self._act_view_image)
        compare_submenu.addAction(self._act_view_image)

        view_menu.addSeparator()

        self._act_show_identical = QAction("Show Identical", self)
        self._act_show_identical.setCheckable(True)
        self._act_show_identical.setChecked(True)
        view_menu.addAction(self._act_show_identical)

        self._act_show_different = QAction("Show Different", self)
        self._act_show_different.setCheckable(True)
        self._act_show_different.setChecked(True)
        view_menu.addAction(self._act_show_different)

        self._act_show_left_only = QAction("Show Left Only", self)
        self._act_show_left_only.setCheckable(True)
        self._act_show_left_only.setChecked(True)
        view_menu.addAction(self._act_show_left_only)

        self._act_show_right_only = QAction("Show Right Only", self)
        self._act_show_right_only.setCheckable(True)
        self._act_show_right_only.setChecked(True)
        view_menu.addAction(self._act_show_right_only)

        # -- Session ----------------------------------------------------
        session_menu = menu_bar.addMenu("&Session")

        self._act_save_profile = QAction("Save Profile", self)
        session_menu.addAction(self._act_save_profile)

        self._act_load_profile = QAction("Load Profile", self)
        session_menu.addAction(self._act_load_profile)

        # -- Tools ------------------------------------------------------
        tools_menu = menu_bar.addMenu("&Tools")

        self._act_sync = QAction("Sync", self)
        tools_menu.addAction(self._act_sync)

        tools_menu.addSeparator()

        self._act_options = QAction("Options", self)
        tools_menu.addAction(self._act_options)

        # -- Help -------------------------------------------------------
        help_menu = menu_bar.addMenu("&Help")

        self._act_about = QAction("About", self)
        help_menu.addAction(self._act_about)

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # New
        self._tb_new = QAction("New", self)
        toolbar.addAction(self._tb_new)

        # Refresh
        self._tb_refresh = QAction("Refresh", self)
        self._tb_refresh.setShortcut(QKeySequence(Qt.Key.Key_F5))
        toolbar.addAction(self._tb_refresh)

        # Compare (primary style via bold text)
        self._tb_compare = QAction("Compare", self)
        toolbar.addAction(self._tb_compare)

        # Cancel
        self._tb_cancel = QAction("Cancel", self)
        self._tb_cancel.setEnabled(False)
        toolbar.addAction(self._tb_cancel)

        toolbar.addSeparator()

        # 3-Way toggle
        self._tb_three_way = QAction("3-Way", self)
        self._tb_three_way.setCheckable(True)
        toolbar.addAction(self._tb_three_way)

        toolbar.addSeparator()

        # Expand All / Collapse All
        self._tb_expand_all = QAction("Expand All", self)
        toolbar.addAction(self._tb_expand_all)

        self._tb_collapse_all = QAction("Collapse All", self)
        toolbar.addAction(self._tb_collapse_all)

        toolbar.addSeparator()

        # Copy actions
        self._tb_copy_lr = QAction("Copy L>R", self)
        toolbar.addAction(self._tb_copy_lr)

        self._tb_copy_rl = QAction("Copy R>L", self)
        toolbar.addAction(self._tb_copy_rl)

        # Sync
        self._tb_sync = QAction("Sync", self)
        toolbar.addAction(self._tb_sync)

        toolbar.addSeparator()

        # Profiles / Options
        self._tb_profiles = QAction("Profiles", self)
        toolbar.addAction(self._tb_profiles)

        self._tb_options = QAction("Options", self)
        toolbar.addAction(self._tb_options)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _build_central_widget(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Path bar
        self._path_bar = PathBar(central)
        layout.addWidget(self._path_bar)

        # View-switcher tab bar
        self._view_switcher = QTabBar(central)
        self._view_switcher.addTab("Folder Compare")
        self._view_switcher.addTab("Text Compare")
        self._view_switcher.addTab("Hex Compare")
        self._view_switcher.addTab("Image Compare")
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

        # FilterBar -> FolderView
        self._filter_bar.filters_changed.connect(self._on_filters_changed)

        # Toolbar / menu actions
        self._tb_compare.triggered.connect(self._on_compare)
        self._tb_cancel.triggered.connect(self._on_cancel)
        self._tb_refresh.triggered.connect(self._on_refresh)
        self._tb_new.triggered.connect(self._on_new_session)
        self._act_new_session.triggered.connect(self._on_new_session)
        self._tb_expand_all.triggered.connect(self._folder_view.expand_all)
        self._tb_collapse_all.triggered.connect(self._folder_view.collapse_all)

        # Copy actions (menu + toolbar)
        self._act_copy_lr.triggered.connect(self._on_copy_lr)
        self._act_copy_rl.triggered.connect(self._on_copy_rl)
        self._tb_copy_lr.triggered.connect(self._on_copy_lr)
        self._tb_copy_rl.triggered.connect(self._on_copy_rl)

        # Sync
        self._act_sync.triggered.connect(self._on_sync)
        self._tb_sync.triggered.connect(self._on_sync)

        # Options / Settings
        self._act_options.triggered.connect(self._on_options)
        self._tb_options.triggered.connect(self._on_options)

        # Profiles
        self._act_save_profile.triggered.connect(self._on_save_profile)
        self._act_load_profile.triggered.connect(self._on_load_profile)
        self._tb_profiles.triggered.connect(self._on_load_profile)

        # About
        self._act_about.triggered.connect(self._on_about)

        # Exit
        self._act_exit.triggered.connect(self.close)

        # FolderView file activated -> detect type and switch view
        self._folder_view.file_activated.connect(self._on_file_activated)

        # View switcher tab bar <-> stacked widget
        self._view_switcher.currentChanged.connect(self._on_view_tab_changed)

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
    # Path slots
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_left_path_changed(self, path: str) -> None:
        self._left_path = path

    @Slot(str)
    def _on_right_path_changed(self, path: str) -> None:
        self._right_path = path

    @Slot(str)
    def _on_base_path_changed(self, path: str) -> None:
        self._base_path = path

    # ------------------------------------------------------------------
    # Filter slots
    # ------------------------------------------------------------------

    @Slot(bool, bool, bool, bool, str)
    def _on_filters_changed(
        self,
        show_identical: bool,
        show_different: bool,
        show_left_only: bool,
        show_right_only: bool,
        search_text: str,
    ) -> None:
        self._folder_view.set_filters(
            show_identical, show_different, show_left_only, show_right_only, search_text,
        )

    @Slot()
    def _on_view_filter_toggled(self) -> None:
        """Sync the View menu filter checkboxes into the FilterBar."""
        self._filter_bar.show_identical = self._act_show_identical.isChecked()
        self._filter_bar.show_different = self._act_show_different.isChecked()
        self._filter_bar.show_left_only = self._act_show_left_only.isChecked()
        self._filter_bar.show_right_only = self._act_show_right_only.isChecked()

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @Slot()
    def _on_compare(self) -> None:
        """Validate paths and launch an asynchronous comparison."""
        left = self._path_bar.left_path.strip()
        right = self._path_bar.right_path.strip()

        if not left or not right:
            QMessageBox.warning(
                self, "Missing Paths", "Please specify both left and right paths."
            )
            return

        left_path = Path(left)
        right_path = Path(right)

        if not left_path.exists():
            QMessageBox.critical(
                self, "Path Not Found", f"Left path does not exist:\n{left}"
            )
            return
        if not right_path.exists():
            QMessageBox.critical(
                self, "Path Not Found", f"Right path does not exist:\n{right}"
            )
            return

        if self._cli_bridge is None:
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
        self.statusBar().showMessage("Starting comparison...")

        self._worker.start_scan(
            left=left,
            right=right,
            follow_symlinks=self._settings.follow_symlinks,
            verify_hashes=self._settings.use_hash_verification,
            ignore_patterns=self._settings.ignore_patterns or None,
        )

    @Slot()
    def _on_cancel(self) -> None:
        """Cancel a running comparison."""
        if self._worker is not None:
            self._worker.cancel()
        self._tb_cancel.setEnabled(False)
        self._tb_compare.setEnabled(True)
        self._status_summary.setText("Cancelled")
        self.statusBar().showMessage("Comparison cancelled.", 5000)

    @Slot(object)
    def _on_comparison_finished(self, report: ScanReport) -> None:
        """Handle a completed comparison."""
        self._current_report = report
        self._tb_cancel.setEnabled(False)
        self._tb_compare.setEnabled(True)

        root: TreeNode = build_tree(report)
        self._folder_view.set_tree(root)

        summary = report.summary
        status_text = (
            f"{summary.same} identical, "
            f"{summary.different} different, "
            f"{summary.orphan_left} left only, "
            f"{summary.orphan_right} right only"
        )
        self._status_summary.setText(status_text)
        self.statusBar().showMessage("Comparison complete.", 5000)

    @Slot(str)
    def _on_comparison_error(self, message: str) -> None:
        """Handle a comparison error."""
        self._tb_cancel.setEnabled(False)
        self._tb_compare.setEnabled(True)
        self._status_summary.setText("Error")
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
    def _on_new_session(self) -> None:
        """Clear all state for a fresh session."""
        # Cancel any running comparison
        if self._worker is not None and self._worker.is_running():
            self._worker.cancel()

        self._path_bar.left_path = ""
        self._path_bar.right_path = ""
        self._path_bar.base_path = ""
        self._left_path = ""
        self._right_path = ""
        self._base_path = ""

        self._current_report = None
        self._folder_view.set_tree(
            TreeNode(name="", path="", status=DiffStatus.SAME, is_dir=True)
        )

        self._status_summary.setText("Ready")
        self.statusBar().clearMessage()
        self._switch_view(0)

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_view_tab_changed(self, index: int) -> None:
        """Synchronise the stacked widget and radio actions with the tab bar."""
        self._view_stack.setCurrentIndex(index)
        actions = [
            self._act_view_folder,
            self._act_view_text,
            self._act_view_hex,
            self._act_view_image,
        ]
        if 0 <= index < len(actions):
            actions[index].setChecked(True)

    def _switch_view(self, index: int) -> None:
        """Programmatically switch the current view."""
        self._view_stack.setCurrentIndex(index)
        self._view_switcher.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # File activation (double-click in FolderView)
    # ------------------------------------------------------------------

    @Slot(str, bool)
    def _on_file_activated(self, path: str, is_dir: bool) -> None:
        """When the user double-clicks a file, detect its type and switch view."""
        if is_dir:
            # Directories stay in the folder view
            return

        suffix = Path(path).suffix.lower()

        if suffix in TEXT_EXTENSIONS:
            self._switch_view(1)
        elif suffix in IMAGE_EXTENSIONS:
            self._switch_view(3)
        else:
            # Default to hex view for binary / unknown files
            self._switch_view(2)

    # ------------------------------------------------------------------
    # 3-Way toggle
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_three_way_toggled(self, checked: bool) -> None:
        self._three_way_mode = checked
        self._path_bar.set_three_way_mode(checked)

    # ------------------------------------------------------------------
    # Copy actions (placeholders)
    # ------------------------------------------------------------------

    @Slot()
    def _on_copy_lr(self) -> None:
        QMessageBox.information(
            self, "Not Implemented", "Copy Left to Right is not implemented yet."
        )

    @Slot()
    def _on_copy_rl(self) -> None:
        QMessageBox.information(
            self, "Not Implemented", "Copy Right to Left is not implemented yet."
        )

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    @Slot()
    def _on_sync(self) -> None:
        """Open the Sync dialog."""
        dialog = SyncDialog(self)
        dialog.exec()

    @Slot()
    def _on_options(self) -> None:
        """Open the Settings dialog and apply changes on accept."""
        dialog = SettingsDialog(self._config, self._settings, self)
        if dialog.exec():
            # Re-read settings that may have changed
            self._settings = dialog.settings()
            # Update CLI bridge if path changed
            try:
                cli_path = self._config.get_cli_path()
                self._cli_bridge = CliBridge(cli_path)
            except FileNotFoundError:
                self._cli_bridge = None

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

    @Slot()
    def _on_load_profile(self) -> None:
        """Open the Profiles dialog to load a session profile."""
        dialog = ProfilesDialog(self._profile_manager, self)
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
                self.statusBar().showMessage(
                    f"Profile '{profile.name}' loaded.", 5000,
                )

    @Slot()
    def _on_about(self) -> None:
        """Open the About dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Close event -- persist geometry
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Save window geometry to config before closing."""
        geom = self.geometry()
        self._config.window_geometry = {
            "x": geom.x(),
            "y": geom.y(),
            "width": geom.width(),
            "height": geom.height(),
        }
        self._config.save()
        super().closeEvent(event)
