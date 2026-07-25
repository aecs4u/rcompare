"""PathBar widget for left/right (and optional base) path selection."""

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPalette
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from ..widgets.breadcrumb_bar import BreadcrumbBar

# Slint color scheme
COLOR_LEFT = "#5a9ed8"
COLOR_RIGHT = "#d85a6a"
COLOR_BASE = "#4caf50"

ARCHIVE_FILTER = (
    "Archives (*.zip *.tar *.tar.gz *.tar.bz2 *.tar.xz *.7z);;All Files (*)"
)


class _DroppableLineEdit(QLineEdit):
    """A QLineEdit that accepts drag-and-drop of folder/file URLs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
                self.setText(path)
                self.editingFinished.emit()
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


def _make_indicator(text: str, color: str) -> QLabel:
    """Create a small colored label used as a row indicator."""
    label = QLabel(text)
    label.setFixedWidth(50)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setAutoFillBackground(True)
    palette = label.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(color))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
    label.setPalette(palette)
    label.setStyleSheet(
        f"background-color: {color}; color: #ffffff; border-radius: 3px;"
        " font-weight: bold; padding: 2px 6px;"
    )
    return label


class PathBar(QWidget):
    """Widget providing path entry rows for left, right, and optional base paths."""

    left_path_changed = Signal(str)
    right_path_changed = Signal(str)
    base_path_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._three_way = False

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)

        # --- Left row (row 0) ---
        self._left_indicator = _make_indicator("Left", COLOR_LEFT)
        self._left_edit = _DroppableLineEdit()
        self._left_edit.setPlaceholderText("Left path...")
        self._left_breadcrumb = BreadcrumbBar()
        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self._left_breadcrumb)  # 0 = breadcrumb
        self._left_stack.addWidget(self._left_edit)         # 1 = line edit
        self._left_stack.setCurrentIndex(0)
        self._left_browse_folder = QPushButton("Browse Folder")
        self._left_browse_archive = QPushButton("Browse Archive")

        self._layout.addWidget(self._left_indicator, 0, 0)
        self._layout.addWidget(self._left_stack, 0, 1)
        self._layout.addWidget(self._left_browse_folder, 0, 2)
        self._layout.addWidget(self._left_browse_archive, 0, 3)

        # --- Right row (row 1) ---
        self._right_indicator = _make_indicator("Right", COLOR_RIGHT)
        self._right_edit = _DroppableLineEdit()
        self._right_edit.setPlaceholderText("Right path...")
        self._right_breadcrumb = BreadcrumbBar()
        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self._right_breadcrumb)
        self._right_stack.addWidget(self._right_edit)
        self._right_stack.setCurrentIndex(0)
        self._right_browse_folder = QPushButton("Browse Folder")
        self._right_browse_archive = QPushButton("Browse Archive")

        self._layout.addWidget(self._right_indicator, 1, 0)
        self._layout.addWidget(self._right_stack, 1, 1)
        self._layout.addWidget(self._right_browse_folder, 1, 2)
        self._layout.addWidget(self._right_browse_archive, 1, 3)

        # --- Base row (row 2, hidden by default) ---
        self._base_indicator = _make_indicator("Base", COLOR_BASE)
        self._base_edit = _DroppableLineEdit()
        self._base_edit.setPlaceholderText("Base path...")
        self._base_breadcrumb = BreadcrumbBar()
        self._base_stack = QStackedWidget()
        self._base_stack.addWidget(self._base_breadcrumb)
        self._base_stack.addWidget(self._base_edit)
        self._base_stack.setCurrentIndex(0)
        self._base_browse_folder = QPushButton("Browse Folder")
        self._base_browse_archive = QPushButton("Browse Archive")

        self._layout.addWidget(self._base_indicator, 2, 0)
        self._layout.addWidget(self._base_stack, 2, 1)
        self._layout.addWidget(self._base_browse_folder, 2, 2)
        self._layout.addWidget(self._base_browse_archive, 2, 3)

        # Hide the base row initially
        self._set_base_row_visible(False)

        # Let the path QLineEdit column stretch
        self._layout.setColumnStretch(1, 1)

        # --- Connections ---

        # Left
        self._left_edit.editingFinished.connect(
            lambda: self._on_edit_finished(
                self._left_edit, self._left_breadcrumb, self.left_path_changed.emit
            )
        )
        self._left_breadcrumb.path_changed.connect(
            lambda p: self._on_breadcrumb_changed(
                p, self._left_edit, self.left_path_changed.emit
            )
        )
        self._left_browse_folder.clicked.connect(self._browse_left_folder)
        self._left_browse_archive.clicked.connect(self._browse_left_archive)

        # Right
        self._right_edit.editingFinished.connect(
            lambda: self._on_edit_finished(
                self._right_edit, self._right_breadcrumb, self.right_path_changed.emit
            )
        )
        self._right_breadcrumb.path_changed.connect(
            lambda p: self._on_breadcrumb_changed(
                p, self._right_edit, self.right_path_changed.emit
            )
        )
        self._right_browse_folder.clicked.connect(self._browse_right_folder)
        self._right_browse_archive.clicked.connect(self._browse_right_archive)

        # Base
        self._base_edit.editingFinished.connect(
            lambda: self._on_edit_finished(
                self._base_edit, self._base_breadcrumb, self.base_path_changed.emit
            )
        )
        self._base_breadcrumb.path_changed.connect(
            lambda p: self._on_breadcrumb_changed(
                p, self._base_edit, self.base_path_changed.emit
            )
        )
        self._base_browse_folder.clicked.connect(self._browse_base_folder)
        self._base_browse_archive.clicked.connect(self._browse_base_archive)

    # ------------------------------------------------------------------
    # Three-way mode
    # ------------------------------------------------------------------

    def set_three_way_mode(self, enabled: bool) -> None:
        """Show or hide the base path row for three-way comparison."""
        self._three_way = enabled
        self._set_base_row_visible(enabled)

    def _set_base_row_visible(self, visible: bool) -> None:
        self._base_indicator.setVisible(visible)
        self._base_stack.setVisible(visible)
        self._base_browse_folder.setVisible(visible)
        self._base_browse_archive.setVisible(visible)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def left_path(self) -> str:
        return self._left_edit.text()

    @left_path.setter
    def left_path(self, value: str) -> None:
        self._left_edit.setText(value)
        self._left_breadcrumb.path = value
        self.left_path_changed.emit(value)

    @property
    def right_path(self) -> str:
        return self._right_edit.text()

    @right_path.setter
    def right_path(self, value: str) -> None:
        self._right_edit.setText(value)
        self._right_breadcrumb.path = value
        self.right_path_changed.emit(value)

    @property
    def base_path(self) -> str:
        return self._base_edit.text()

    @base_path.setter
    def base_path(self, value: str) -> None:
        self._base_edit.setText(value)
        self._base_breadcrumb.path = value
        self.base_path_changed.emit(value)

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _on_edit_finished(
        self,
        edit: QLineEdit,
        breadcrumb: BreadcrumbBar,
        emit: Callable[[str], None],
    ) -> None:
        """Sync breadcrumb when line edit is committed."""
        text = edit.text()
        breadcrumb.path = text
        emit(text)

    def _on_breadcrumb_changed(
        self, path: str, edit: QLineEdit, emit: Callable[[str], None]
    ) -> None:
        """Sync line edit when breadcrumb is clicked."""
        edit.setText(path)
        emit(path)

    def _browse_folder(
        self,
        line_edit: QLineEdit,
        breadcrumb: BreadcrumbBar,
        emit: Callable[[str], None],
    ) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Folder", line_edit.text()
        )
        if path:
            line_edit.setText(path)
            breadcrumb.path = path
            emit(path)

    def _browse_archive(
        self,
        line_edit: QLineEdit,
        breadcrumb: BreadcrumbBar,
        emit: Callable[[str], None],
    ) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Archive", line_edit.text(), ARCHIVE_FILTER
        )
        if path:
            line_edit.setText(path)
            breadcrumb.path = path
            emit(path)

    # Left
    def _browse_left_folder(self) -> None:
        self._browse_folder(
            self._left_edit, self._left_breadcrumb, self.left_path_changed.emit
        )

    def _browse_left_archive(self) -> None:
        self._browse_archive(
            self._left_edit, self._left_breadcrumb, self.left_path_changed.emit
        )

    # Right
    def _browse_right_folder(self) -> None:
        self._browse_folder(
            self._right_edit, self._right_breadcrumb, self.right_path_changed.emit
        )

    def _browse_right_archive(self) -> None:
        self._browse_archive(
            self._right_edit, self._right_breadcrumb, self.right_path_changed.emit
        )

    # Base
    def _browse_base_folder(self) -> None:
        self._browse_folder(
            self._base_edit, self._base_breadcrumb, self.base_path_changed.emit
        )

    def _browse_base_archive(self) -> None:
        self._browse_archive(
            self._base_edit, self._base_breadcrumb, self.base_path_changed.emit
        )
