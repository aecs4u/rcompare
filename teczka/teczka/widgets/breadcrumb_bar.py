"""BreadcrumbBar widget providing Beyond Compare-style breadcrumb path navigation."""

from __future__ import annotations

import os

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QWidget,
)


class BreadcrumbBar(QWidget):
    """A breadcrumb path navigation bar with inline editing support.

    Displays a file path as clickable breadcrumb segments. Each segment
    represents a directory component. Clicking a segment navigates to
    the path up to and including that segment.

    A toggle button switches between breadcrumb mode and raw text editing
    mode (QLineEdit). Drag-and-drop of file/folder URLs is also supported.

    Signals:
        path_changed(str): Emitted when the path changes via breadcrumb
            click, text edit, or drag-and-drop.
    """

    path_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: str = ""
        self._editing: bool = False

        self.setAcceptDrops(True)

        # --- Main layout ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Scroll area for breadcrumb segments ---
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        # No horizontal scrollbar: it renders inside the row's fixed height and
        # clips the segment labels from below. Overflow is handled by
        # auto-scrolling to the deepest segment, as file-manager breadcrumbs do.
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._breadcrumb_container = QWidget()
        self._breadcrumb_layout = QHBoxLayout(self._breadcrumb_container)
        self._breadcrumb_layout.setContentsMargins(2, 0, 2, 0)
        self._breadcrumb_layout.setSpacing(0)
        self._breadcrumb_layout.addStretch()
        self._scroll_area.setWidget(self._breadcrumb_container)

        # --- Line edit for raw editing mode ---
        self._line_edit = QLineEdit()
        self._line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._line_edit.returnPressed.connect(self._on_edit_finished)
        self._line_edit.editingFinished.connect(self._on_edit_finished)
        self._line_edit.setVisible(False)

        # --- Toggle button ---
        self._edit_button = QToolButton()
        self._edit_button.setText("\u270e")  # pencil icon
        self._edit_button.setToolTip("Toggle path editing")
        self._edit_button.setCheckable(True)
        self._edit_button.setFixedSize(24, 24)
        self._edit_button.setStyleSheet(
            "QToolButton { border: 1px solid palette(mid);"
            " border-radius: 3px; background: palette(button); }"
            "QToolButton:checked { background: palette(highlight);"
            " color: palette(highlighted-text); }"
            "QToolButton:hover { background: palette(light); }"
        )
        self._edit_button.toggled.connect(self._toggle_edit_mode)

        main_layout.addWidget(self._scroll_area, 1)
        main_layout.addWidget(self._line_edit, 1)
        main_layout.addWidget(self._edit_button, 0)

        # Keep height compact, but never shorter than what the row actually
        # needs: a hardcoded or line-edit-only height clips segment descenders
        # once the font is scaled up (HiDPI, large-text accessibility setting).
        ref = QLineEdit()
        ref.ensurePolished()
        self._line_edit.ensurePolished()
        h = max(
            ref.sizeHint().height(),
            self._line_edit.sizeHint().height(),
            self._edit_button.height(),
            self.fontMetrics().height() + 8,
        )
        self.setFixedHeight(h)
        self._scroll_area.setFixedHeight(h)

    # ------------------------------------------------------------------
    # Public property
    # ------------------------------------------------------------------

    @property
    def path(self) -> str:
        """Return the currently displayed path."""
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        """Set the displayed path and rebuild the breadcrumb segments."""
        normalised = os.path.normpath(value) if value else ""
        if normalised == self._path:
            return
        self._path = normalised
        self._rebuild_breadcrumbs()

    # ------------------------------------------------------------------
    # Breadcrumb construction
    # ------------------------------------------------------------------

    def _rebuild_breadcrumbs(self) -> None:
        """Clear and recreate breadcrumb buttons from the current path."""
        # Remove existing widgets from layout.
        while self._breadcrumb_layout.count():
            item = self._breadcrumb_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self._path:
            self._breadcrumb_layout.addStretch()
            return

        parts = self._split_path(self._path)

        for index, (label_text, accumulated_path) in enumerate(parts):
            if index > 0:
                sep = QLabel("/")
                sep.setStyleSheet(
                    "QLabel { color: palette(mid); padding: 0 2px; }"
                )
                self._breadcrumb_layout.addWidget(sep)

            btn = QPushButton(label_text)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(
                "QPushButton { border: none; padding: 1px 4px;"
                " color: palette(link); background: transparent; }"
                "QPushButton:hover { text-decoration: underline;"
                " background: palette(midlight); border-radius: 3px; }"
            )
            # Capture accumulated_path in the closure via default argument.
            btn.clicked.connect(
                lambda _checked=False, p=accumulated_path: self._on_segment_clicked(p)
            )
            self._breadcrumb_layout.addWidget(btn)

        self._breadcrumb_layout.addStretch()

        # Scroll to the right so the deepest segment is visible.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._scroll_to_end)

    def _scroll_to_end(self) -> None:
        """Scroll the breadcrumb area to the rightmost end."""
        sb = self._scroll_area.horizontalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    @staticmethod
    def _split_path(path: str) -> list[tuple[str, str]]:
        """Split *path* into ``(display_label, accumulated_path)`` pairs.

        On Unix the root is shown as ``/``.  On Windows the drive letter
        (e.g. ``C:\\``) is used as the root label.
        """
        parts: list[tuple[str, str]] = []

        # Normalise separators.
        path = path.replace("\\", "/")

        # Detect Windows drive root (e.g. "C:/").
        drive = ""
        if len(path) >= 2 and path[1] == ":":
            drive = path[:2]  # e.g. "C:"
            remainder = path[2:]
        else:
            remainder = path

        # Strip leading slashes to get individual components.
        remainder = remainder.lstrip("/")
        components = remainder.split("/") if remainder else []

        # Build root segment.
        if drive:
            root_path = drive + os.sep
            root_label = drive + os.sep
        else:
            root_path = os.sep
            root_label = os.sep
        parts.append((root_label, root_path))

        # Build subsequent segments.
        accumulated = root_path
        for comp in components:
            if not comp:
                continue
            accumulated = os.path.join(accumulated, comp)
            parts.append((comp, accumulated))

        return parts

    # ------------------------------------------------------------------
    # Editing mode
    # ------------------------------------------------------------------

    def _toggle_edit_mode(self, editing: bool) -> None:
        """Switch between breadcrumb view and line-edit view."""
        self._editing = editing
        self._scroll_area.setVisible(not editing)
        self._line_edit.setVisible(editing)

        if editing:
            self._line_edit.setText(self._path)
            self._line_edit.setFocus()
            self._line_edit.selectAll()

    def _on_edit_finished(self) -> None:
        """Handle the user finishing text input (Enter or focus loss)."""
        if not self._editing:
            return

        new_path = self._line_edit.text().strip()
        # Switch back to breadcrumb mode.
        self._edit_button.setChecked(False)  # triggers _toggle_edit_mode(False)

        if new_path and new_path != self._path:
            self.path = new_path
            self.path_changed.emit(self._path)

    def _on_segment_clicked(self, segment_path: str) -> None:
        """Handle a breadcrumb segment being clicked."""
        if segment_path != self._path:
            self.path = segment_path
            self.path_changed.emit(self._path)

    # ------------------------------------------------------------------
    # Drag-and-drop support
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Accept drag events that carry file or directory URLs."""
        mime: QMimeData | None = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Handle a drop event by updating the path to the dropped URL."""
        mime: QMimeData | None = event.mimeData()
        if mime is None or not mime.hasUrls():
            super().dropEvent(event)
            return

        urls = mime.urls()
        if not urls:
            super().dropEvent(event)
            return

        dropped_path = urls[0].toLocalFile()
        if dropped_path:
            # If the dropped item is a file, use its parent directory.
            if os.path.isfile(dropped_path):
                dropped_path = os.path.dirname(dropped_path)
            self.path = dropped_path
            self.path_changed.emit(self._path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
