"""Configure Keyboard Shortcuts dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ShortcutsDialog(QDialog):
    """KDE-style dialog for viewing and editing keyboard shortcuts."""

    def __init__(self, main_window: QMainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent or main_window)
        self.setWindowTitle("Configure Keyboard Shortcuts")
        self.setMinimumSize(640, 480)
        self._main_window = main_window
        self._changes: dict[str, QKeySequence] = {}
        self._actions: list[QAction] = []
        self._originals: dict[QAction, QKeySequence] = {}

        layout = QVBoxLayout(self)

        # Search filter
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter actions...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._filter_actions)
        search_row.addWidget(self._search_edit, 1)
        layout.addLayout(search_row)

        # Action tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Action", "Shortcut"])
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        header = self._tree.header()
        if header is not None:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree, 1)

        # Shortcut editor row
        editor_row = QHBoxLayout()
        editor_row.addWidget(QLabel("Shortcut:"))
        self._key_edit = QKeySequenceEdit()
        self._key_edit.setEnabled(False)
        editor_row.addWidget(self._key_edit, 1)
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_shortcut)
        editor_row.addWidget(self._apply_btn)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._clear_shortcut)
        editor_row.addWidget(self._clear_btn)
        layout.addLayout(editor_row)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_actions()

    def _populate_actions(self) -> None:
        """Scan all menus and populate the tree."""
        menubar = self._main_window.menuBar()
        if menubar is None:
            return

        for menu_action in menubar.actions():
            menu = menu_action.menu()
            if menu is None:
                continue
            menu_item = QTreeWidgetItem(self._tree, [menu_action.text().replace("&", "")])
            menu_item.setFlags(menu_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for action in menu.actions():
                if action.isSeparator():
                    continue
                submenu = action.menu()
                if submenu:
                    sub_item = QTreeWidgetItem(menu_item, [action.text().replace("&", "")])
                    sub_item.setFlags(sub_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    for sub_action in submenu.actions():
                        if sub_action.isSeparator():
                            continue
                        self._add_action_item(sub_item, sub_action)
                else:
                    self._add_action_item(menu_item, action)

            menu_item.setExpanded(True)

    def _add_action_item(self, parent: QTreeWidgetItem, action: QAction) -> None:
        """Add a single action as a tree item."""
        name = action.text().replace("&", "")
        if not name:
            return
        shortcut = action.shortcut().toString() if action.shortcut() else ""
        item = QTreeWidgetItem(parent, [name, shortcut])
        item.setData(0, Qt.ItemDataRole.UserRole, action)
        self._actions.append(action)
        self._originals[action] = action.shortcut()

    def _on_item_changed(self, current: QTreeWidgetItem | None, _prev: QTreeWidgetItem | None) -> None:
        """Enable editor when an action item is selected."""
        if current is None:
            self._key_edit.setEnabled(False)
            self._apply_btn.setEnabled(False)
            self._clear_btn.setEnabled(False)
            return
        action = current.data(0, Qt.ItemDataRole.UserRole)
        has_action = action is not None
        self._key_edit.setEnabled(has_action)
        self._apply_btn.setEnabled(has_action)
        self._clear_btn.setEnabled(has_action)
        if has_action:
            self._key_edit.setKeySequence(action.shortcut())

    def _apply_shortcut(self) -> None:
        """Apply the edited shortcut to the selected action."""
        item = self._tree.currentItem()
        if item is None:
            return
        action: QAction | None = item.data(0, Qt.ItemDataRole.UserRole)
        if action is None:
            return
        new_seq = self._key_edit.keySequence()
        action.setShortcut(new_seq)
        item.setText(1, new_seq.toString())
        self._changes[action.text()] = new_seq

    def _clear_shortcut(self) -> None:
        """Clear the shortcut for the selected action."""
        self._key_edit.clear()
        item = self._tree.currentItem()
        if item is None:
            return
        action: QAction | None = item.data(0, Qt.ItemDataRole.UserRole)
        if action is None:
            return
        action.setShortcut(QKeySequence())
        item.setText(1, "")
        self._changes[action.text()] = QKeySequence()

    def _filter_actions(self, text: str) -> None:
        """Filter visible actions by search text."""
        search = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            menu_item = self._tree.topLevelItem(i)
            if menu_item is None:
                continue
            any_visible = False
            for j in range(menu_item.childCount()):
                child = menu_item.child(j)
                if child is None:
                    continue
                # Check if it's a submenu
                if child.childCount() > 0:
                    sub_visible = False
                    for k in range(child.childCount()):
                        sub = child.child(k)
                        if sub is None:
                            continue
                        visible = not search or search in sub.text(0).lower() or search in sub.text(1).lower()
                        sub.setHidden(not visible)
                        sub_visible = sub_visible or visible
                    child.setHidden(not sub_visible)
                    any_visible = any_visible or sub_visible
                else:
                    visible = not search or search in child.text(0).lower() or search in child.text(1).lower()
                    child.setHidden(not visible)
                    any_visible = any_visible or visible
            menu_item.setHidden(not any_visible)

    def accept(self) -> None:
        """Reject duplicate bindings before committing the live edits."""
        by_shortcut: dict[str, list[str]] = {}
        for action in self._actions:
            sequence = action.shortcut()
            if sequence.isEmpty():
                continue
            chord = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            by_shortcut.setdefault(chord, []).append(
                action.text().replace("&", "").strip()
            )
        collisions = {
            chord: labels
            for chord, labels in by_shortcut.items()
            if len(labels) > 1
        }
        if collisions:
            details = "\n".join(
                f"{chord}: {', '.join(labels)}"
                for chord, labels in sorted(collisions.items())
            )
            QMessageBox.warning(
                self,
                "Shortcut Collision",
                f"Each shortcut must be unique:\n\n{details}",
            )
            return
        super().accept()

    def reject(self) -> None:
        """Restore shortcuts changed through Apply/Clear when Cancel is used."""
        for action, sequence in self._originals.items():
            action.setShortcut(sequence)
        super().reject()

    def shortcut_map(self) -> dict[str, str]:
        """Return persisted action-label to portable shortcut mappings."""
        return {
            action.text().replace("&", "").strip(): action.shortcut().toString(
                QKeySequence.SequenceFormat.PortableText
            )
            for action in self._actions
        }
