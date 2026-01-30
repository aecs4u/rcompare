"""Session profile management dialog for RCompare."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QGroupBox, QFormLayout, QPushButton, QInputDialog,
    QMessageBox, QWidget,
)

from ..models.settings import ProfileManager, SessionProfile


class ProfilesDialog(QDialog):
    """Dialog for managing session profiles."""

    profile_loaded = Signal(str, str)  # left_path, right_path

    def __init__(
        self,
        profile_manager: ProfileManager,
        left_path: str = "",
        right_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Session Profiles")
        self.setMinimumSize(550, 380)
        self._manager = profile_manager
        self._left_path = left_path
        self._right_path = right_path

        layout = QHBoxLayout(self)

        # Left side: profile list
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("Profiles:"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        left_panel.addWidget(self._list)
        layout.addLayout(left_panel, 1)

        # Right side: details + buttons
        right_panel = QVBoxLayout()

        details_group = QGroupBox("Details")
        details_layout = QFormLayout(details_group)
        self._name_label = QLabel("")
        self._left_label = QLabel("")
        self._right_label = QLabel("")
        self._last_used_label = QLabel("")
        details_layout.addRow("Name:", self._name_label)
        details_layout.addRow("Left path:", self._left_label)
        details_layout.addRow("Right path:", self._right_label)
        details_layout.addRow("Last used:", self._last_used_label)
        right_panel.addWidget(details_group)

        right_panel.addStretch()

        # Buttons
        button_layout = QVBoxLayout()
        save_btn = QPushButton("Save Current")
        save_btn.clicked.connect(self._on_save_current)
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._on_load)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._on_delete)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(load_btn)
        button_layout.addWidget(delete_btn)
        button_layout.addWidget(close_btn)
        right_panel.addLayout(button_layout)

        layout.addLayout(right_panel, 1)

        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for profile in self._manager.profiles:
            item = QListWidgetItem(profile.name)
            item.setData(256, profile.id)  # Qt.UserRole == 256
            self._list.addItem(item)

    def _selected_profile(self) -> SessionProfile | None:
        item = self._list.currentItem()
        if item is None:
            return None
        profile_id = item.data(256)
        return self._manager.get(profile_id)

    def _on_selection_changed(self, row: int) -> None:
        profile = self._selected_profile()
        if profile:
            self._name_label.setText(profile.name)
            self._left_label.setText(profile.left_path or "(not set)")
            self._right_label.setText(profile.right_path or "(not set)")
            self._last_used_label.setText(profile.last_used or "Never")
        else:
            self._name_label.setText("")
            self._left_label.setText("")
            self._right_label.setText("")
            self._last_used_label.setText("")

    def _on_save_current(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Save Profile", "Profile name:"
        )
        if not ok or not name.strip():
            return
        profile = SessionProfile(
            name=name.strip(),
            left_path=self._left_path,
            right_path=self._right_path,
            last_used=datetime.now().isoformat(),
        )
        self._manager.add(profile)
        self._refresh_list()

    def _on_load(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "Load Profile", "No profile selected.")
            return
        self.profile_loaded.emit(profile.left_path, profile.right_path)
        self.accept()

    def _on_delete(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "Delete Profile", "No profile selected.")
            return
        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete profile \"{profile.name}\"?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._manager.delete(profile.id)
            self._refresh_list()
