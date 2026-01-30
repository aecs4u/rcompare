"""Binary/hex comparison view with two side-by-side hex panels."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 16  # bytes per row
_INITIAL_LOAD_ROWS = 1024 * 64  # rows loaded initially (~1 MB)
_FETCH_INCREMENT = 1024 * 64  # rows fetched per fetchMore call

_COL_OFFSET = 0
_COL_HEX_START = 1
_COL_HEX_END = 16  # inclusive
_COL_ASCII = 17
_TOTAL_COLUMNS = 18

_DIFF_BG = QColor("#ffe1e1")
_NORMAL_BG = QColor("#ffffff")
_NON_PRINTABLE_FG = QColor("#999999")


def _is_printable(byte: int) -> bool:
    """Return True if *byte* maps to a printable ASCII character."""
    return 0x20 <= byte <= 0x7E


# ---------------------------------------------------------------------------
# HexTableModel
# ---------------------------------------------------------------------------


class HexTableModel(QAbstractTableModel):
    """Table model exposing binary data as hex + ASCII rows.

    Each row represents 16 bytes.  Columns are:
        0        Offset (hex address)
        1..16    Individual hex bytes
        17       ASCII representation

    For files larger than ``_INITIAL_LOAD_ROWS * _CHUNK_SIZE`` bytes the
    model lazily fetches additional rows via :meth:`canFetchMore` /
    :meth:`fetchMore`.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data: bytes = b""
        self._file_path: str = ""
        self._total_rows: int = 0
        self._loaded_rows: int = 0
        self._diff_indices: set[int] = set()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def load_file(self, path: str) -> None:
        """Read binary data from *path* and reset the model."""
        self.beginResetModel()
        try:
            with open(path, "rb") as fh:
                self._data = fh.read()
        except OSError:
            self._data = b""
        self._file_path = path
        self._total_rows = (len(self._data) + _CHUNK_SIZE - 1) // _CHUNK_SIZE
        self._loaded_rows = min(self._total_rows, _INITIAL_LOAD_ROWS)
        self._diff_indices = set()
        self.endResetModel()

    def set_diff_indices(self, indices: set[int]) -> None:
        """Mark byte positions that differ from the other side."""
        self._diff_indices = indices
        if self._loaded_rows > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self._loaded_rows - 1, _TOTAL_COLUMNS - 1)
            self.dataChanged.emit(top_left, bottom_right)

    @property
    def raw_data(self) -> bytes:
        return self._data

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        if parent.isValid():
            return False
        return self._loaded_rows < self._total_rows

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid():
            return
        remaining = self._total_rows - self._loaded_rows
        to_fetch = min(remaining, _FETCH_INCREMENT)
        self.beginInsertRows(QModelIndex(), self._loaded_rows, self._loaded_rows + to_fetch - 1)
        self._loaded_rows += to_fetch
        self.endInsertRows()

    # ------------------------------------------------------------------
    # QAbstractTableModel interface
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return self._loaded_rows

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return _TOTAL_COLUMNS

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if section == _COL_OFFSET:
                return "Offset"
            if _COL_HEX_START <= section <= _COL_HEX_END:
                return f"{section - 1:X}"
            if section == _COL_ASCII:
                return "ASCII"
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        offset = row * _CHUNK_SIZE

        if role == Qt.DisplayRole:
            return self._display_data(row, col, offset)

        if role == Qt.BackgroundRole:
            return self._background_data(row, col, offset)

        if role == Qt.ForegroundRole:
            return self._foreground_data(row, col, offset)

        return None

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _display_data(self, row: int, col: int, offset: int):
        if col == _COL_OFFSET:
            return f"{offset:08X}"

        if _COL_HEX_START <= col <= _COL_HEX_END:
            byte_index = offset + (col - _COL_HEX_START)
            if byte_index < len(self._data):
                return f"{self._data[byte_index]:02X}"
            return ""

        if col == _COL_ASCII:
            chunk = self._data[offset: offset + _CHUNK_SIZE]
            return "".join(
                chr(b) if _is_printable(b) else "." for b in chunk
            )

        return None

    def _background_data(self, row: int, col: int, offset: int):
        if col == _COL_OFFSET:
            return None

        if _COL_HEX_START <= col <= _COL_HEX_END:
            byte_index = offset + (col - _COL_HEX_START)
            if byte_index in self._diff_indices:
                return _DIFF_BG
            return _NORMAL_BG

        if col == _COL_ASCII:
            # Highlight the ASCII cell if any byte in the row differs.
            for i in range(offset, min(offset + _CHUNK_SIZE, len(self._data))):
                if i in self._diff_indices:
                    return _DIFF_BG
            return _NORMAL_BG

        return None

    def _foreground_data(self, row: int, col: int, offset: int):
        if col == _COL_ASCII:
            chunk = self._data[offset: offset + _CHUNK_SIZE]
            # Use darker text if the chunk contains any non-printable chars.
            for b in chunk:
                if not _is_printable(b):
                    return _NON_PRINTABLE_FG
        return None


# ---------------------------------------------------------------------------
# HexView
# ---------------------------------------------------------------------------


class HexView(QWidget):
    """Side-by-side hex comparison widget.

    Two :class:`QTableView` widgets each backed by a :class:`HexTableModel`
    display binary data in the traditional offset / hex bytes / ASCII layout.
    Scrolling is synchronised between the two panels so the user can easily
    spot byte-level differences.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._syncing = False

        # Monospace font used for both tables.
        self._mono_font: QFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)

        # Models -------------------------------------------------------
        self._left_model = HexTableModel(self)
        self._right_model = HexTableModel(self)

        # Path labels --------------------------------------------------
        self._left_path_label = QLabel("(no file loaded)")
        self._right_path_label = QLabel("(no file loaded)")
        self._left_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._right_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # Browse buttons -----------------------------------------------
        self._left_browse_btn = QPushButton("Browse...")
        self._right_browse_btn = QPushButton("Browse...")
        self._left_browse_btn.clicked.connect(self._browse_left)
        self._right_browse_btn.clicked.connect(self._browse_right)

        # Tables -------------------------------------------------------
        self._left_table = self._create_table(self._left_model)
        self._right_table = self._create_table(self._right_model)

        # Synchronised scrolling ---------------------------------------
        left_vbar = self._left_table.verticalScrollBar()
        right_vbar = self._right_table.verticalScrollBar()
        if left_vbar is not None and right_vbar is not None:
            left_vbar.valueChanged.connect(self._on_left_scrolled)
            right_vbar.valueChanged.connect(self._on_right_scrolled)

        # Layout -------------------------------------------------------
        left_header = QHBoxLayout()
        left_header.addWidget(self._left_path_label, stretch=1)
        left_header.addWidget(self._left_browse_btn)

        right_header = QHBoxLayout()
        right_header.addWidget(self._right_path_label, stretch=1)
        right_header.addWidget(self._right_browse_btn)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(left_header)
        left_layout.addWidget(self._left_table)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(right_header)
        right_layout.addWidget(self._right_table)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(QLabel("<b>Hex Compare</b>"))
        main_layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compare_files(self, left_path: str, right_path: str) -> None:
        """Load two files, compute differences, and display the hex views."""
        self._left_model.load_file(left_path)
        self._right_model.load_file(right_path)

        self._left_path_label.setText(os.path.basename(left_path))
        self._left_path_label.setToolTip(left_path)
        self._right_path_label.setText(os.path.basename(right_path))
        self._right_path_label.setToolTip(right_path)

        # Compute difference indices -----------------------------------
        left_data = self._left_model.raw_data
        right_data = self._right_model.raw_data
        max_len = max(len(left_data), len(right_data))

        diff_left: set[int] = set()
        diff_right: set[int] = set()

        for i in range(max_len):
            lb = left_data[i] if i < len(left_data) else -1
            rb = right_data[i] if i < len(right_data) else -1
            if lb != rb:
                if i < len(left_data):
                    diff_left.add(i)
                if i < len(right_data):
                    diff_right.add(i)

        self._left_model.set_diff_indices(diff_left)
        self._right_model.set_diff_indices(diff_right)

    # ------------------------------------------------------------------
    # Table construction
    # ------------------------------------------------------------------

    def _create_table(self, model: HexTableModel) -> QTableView:
        """Build and configure a QTableView for hex display."""
        table = QTableView(self)
        table.setModel(model)
        table.setFont(self._mono_font)
        table.setShowGrid(False)
        table.setSelectionMode(QTableView.NoSelection)
        table.verticalHeader().setVisible(False)

        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.Fixed)

        # Column widths ------------------------------------------------
        table.setColumnWidth(_COL_OFFSET, 80)
        for c in range(_COL_HEX_START, _COL_HEX_END + 1):
            table.setColumnWidth(c, 28)
        table.setColumnWidth(_COL_ASCII, 160)

        return table

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_left(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Left File")
        if path:
            right_path = self._right_model._file_path
            if right_path:
                self.compare_files(path, right_path)
            else:
                self._left_model.load_file(path)
                self._left_path_label.setText(os.path.basename(path))
                self._left_path_label.setToolTip(path)

    def _browse_right(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Right File")
        if path:
            left_path = self._left_model._file_path
            if left_path:
                self.compare_files(left_path, path)
            else:
                self._right_model.load_file(path)
                self._right_path_label.setText(os.path.basename(path))
                self._right_path_label.setToolTip(path)

    # ------------------------------------------------------------------
    # Scroll synchronisation
    # ------------------------------------------------------------------

    def _on_left_scrolled(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            right_vbar = self._right_table.verticalScrollBar()
            if right_vbar is not None:
                right_vbar.setValue(value)
        finally:
            self._syncing = False

    def _on_right_scrolled(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            left_vbar = self._left_table.verticalScrollBar()
            if left_vbar is not None:
                left_vbar.setValue(value)
        finally:
            self._syncing = False
