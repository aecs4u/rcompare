"""Session profile management dialog for RCompare."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
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
        base_path: str = "",
        ignore_patterns: list[str] | None = None,
        follow_symlinks: bool = False,
        hash_verification: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Session Profiles")
        self.setMinimumSize(760, 460)
        self._manager = profile_manager
        self._left_path = left_path
        self._right_path = right_path
        self._base_path = base_path
        self._ignore_patterns = list(ignore_patterns or [])
        self._follow_symlinks = follow_symlinks
        self._hash_verification = hash_verification
        self._loaded_profile_id: str | None = None

        layout = QHBoxLayout(self)

        # Left side: profile list
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("Profiles:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter by name or path...")
        self._filter_edit.textChanged.connect(self._refresh_list)
        left_panel.addWidget(self._filter_edit)
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(lambda _: self._on_load())
        left_panel.addWidget(self._list)
        self._count_label = QLabel("")
        left_panel.addWidget(self._count_label)
        layout.addLayout(left_panel, 1)

        # Right side: details + buttons
        right_panel = QVBoxLayout()

        details_group = QGroupBox("Details")
        details_layout = QFormLayout(details_group)
        self._name_label = QLabel("")
        self._left_label = QLabel("")
        self._right_label = QLabel("")
        self._base_label = QLabel("")
        self._patterns_label = QLabel("")
        self._symlink_label = QLabel("")
        self._hash_label = QLabel("")
        self._last_used_label = QLabel("")
        for label in (
            self._name_label,
            self._left_label,
            self._right_label,
            self._base_label,
            self._patterns_label,
            self._symlink_label,
            self._hash_label,
            self._last_used_label,
        ):
            label.setWordWrap(True)
        details_layout.addRow("Name:", self._name_label)
        details_layout.addRow("Left path:", self._left_label)
        details_layout.addRow("Right path:", self._right_label)
        details_layout.addRow("Base path:", self._base_label)
        details_layout.addRow("Ignore patterns:", self._patterns_label)
        details_layout.addRow("Follow symlinks:", self._symlink_label)
        details_layout.addRow("Hash verification:", self._hash_label)
        details_layout.addRow("Last used:", self._last_used_label)
        right_panel.addWidget(details_group)

        right_panel.addStretch()

        # Buttons
        button_layout = QVBoxLayout()
        self._save_btn = QPushButton("Save Current")
        self._save_btn.clicked.connect(self._on_save_current)
        self._rename_btn = QPushButton("Rename")
        self._rename_btn.clicked.connect(self._on_rename)
        self._duplicate_btn = QPushButton("Duplicate")
        self._duplicate_btn.clicked.connect(self._on_duplicate)
        self._load_btn = QPushButton("Load")
        self._load_btn.clicked.connect(self._on_load)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._save_btn)
        button_layout.addWidget(self._rename_btn)
        button_layout.addWidget(self._duplicate_btn)
        button_layout.addWidget(self._load_btn)
        button_layout.addWidget(self._delete_btn)
        button_layout.addWidget(close_btn)
        right_panel.addLayout(button_layout)

        layout.addLayout(right_panel, 1)

        self._refresh_list()
        self._update_action_buttons()

    def _refresh_list(self, *_args) -> None:
        current_id = None
        current = self._list.currentItem()
        if current is not None:
            current_id = current.data(256)

        all_profiles = sorted(
            self._manager.profiles,
            key=lambda p: (p.last_used or "", p.name.lower()),
            reverse=True,
        )
        filter_text = self._filter_edit.text().strip().lower()
        self._list.clear()
        shown = 0
        for profile in all_profiles:
            haystack = (
                f"{profile.name}\n{profile.left_path}\n{profile.right_path}\n{profile.base_path}"
            ).lower()
            if filter_text and filter_text not in haystack:
                continue
            item = QListWidgetItem(profile.name)
            item.setData(256, profile.id)  # Qt.UserRole == 256
            self._list.addItem(item)
            shown += 1
            if current_id and current_id == profile.id:
                self._list.setCurrentItem(item)

        total = len(all_profiles)
        self._count_label.setText(f"Showing {shown} of {total} profiles")
        if shown > 0 and self._list.currentItem() is None:
            self._list.setCurrentRow(0)
        if shown == 0:
            self._set_details(None)
        self._update_action_buttons()

    def _selected_profile(self) -> SessionProfile | None:
        item = self._list.currentItem()
        if item is None:
            return None
        profile_id = item.data(256)
        return self._manager.get(profile_id)

    def selected_profile(self) -> SessionProfile | None:
        """Public accessor used by MainWindow after dialog acceptance."""
        if self._loaded_profile_id is not None:
            return self._manager.get(self._loaded_profile_id)
        return self._selected_profile()

    def _fmt_timestamp(self, raw: str) -> str:
        if not raw:
            return "Never"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return raw
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _set_details(self, profile: SessionProfile | None) -> None:
        if profile is None:
            self._name_label.setText("")
            self._left_label.setText("")
            self._right_label.setText("")
            self._base_label.setText("")
            self._patterns_label.setText("")
            self._symlink_label.setText("")
            self._hash_label.setText("")
            self._last_used_label.setText("")
            return
        self._name_label.setText(profile.name)
        self._left_label.setText(profile.left_path or "(not set)")
        self._right_label.setText(profile.right_path or "(not set)")
        self._base_label.setText(profile.base_path or "(not set)")
        self._patterns_label.setText(", ".join(profile.ignore_patterns) or "(none)")
        self._symlink_label.setText("Enabled" if profile.follow_symlinks else "Disabled")
        self._hash_label.setText("Enabled" if profile.hash_verification else "Disabled")
        self._last_used_label.setText(self._fmt_timestamp(profile.last_used))

    def _update_action_buttons(self) -> None:
        has_selection = self._selected_profile() is not None
        self._rename_btn.setEnabled(has_selection)
        self._duplicate_btn.setEnabled(has_selection)
        self._load_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

    def _on_selection_changed(self, row: int) -> None:
        _ = row
        self._set_details(self._selected_profile())
        self._update_action_buttons()

    def _default_profile_name(self) -> str:
        left_name = Path(self._left_path).name if self._left_path else "left"
        right_name = Path(self._right_path).name if self._right_path else "right"
        return f"{left_name} <> {right_name}"

    def _persisted(self, saved: bool) -> bool:
        if saved:
            return True
        QMessageBox.warning(
            self,
            "Profile Not Saved",
            self._manager.last_save_error or "The profile file could not be written.",
        )
        return False

    def _on_save_current(self) -> None:
        if not self._left_path.strip() and not self._right_path.strip():
            QMessageBox.information(
                self,
                "Save Profile",
                "Current session has no left/right paths to save.",
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "Save Profile",
            "Profile name:",
            text=self._default_profile_name(),
        )
        if not ok or not name.strip():
            return
        profile = SessionProfile(
            name=name.strip(),
            left_path=self._left_path,
            right_path=self._right_path,
            base_path=self._base_path,
            ignore_patterns=list(self._ignore_patterns),
            follow_symlinks=self._follow_symlinks,
            hash_verification=self._hash_verification,
            last_used=datetime.now().isoformat(),
        )
        if self._persisted(self._manager.add(profile)):
            self._refresh_list()

    def _on_rename(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        name, ok = QInputDialog.getText(
            self,
            "Rename Profile",
            "New profile name:",
            text=profile.name,
        )
        if not ok or not name.strip():
            return
        profile.name = name.strip()
        if self._persisted(self._manager.update(profile)):
            self._refresh_list()

    def _on_duplicate(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        copy_profile = SessionProfile(
            name=f"{profile.name} (copy)",
            left_path=profile.left_path,
            right_path=profile.right_path,
            base_path=profile.base_path,
            ignore_patterns=list(profile.ignore_patterns),
            follow_symlinks=profile.follow_symlinks,
            hash_verification=profile.hash_verification,
            last_used=datetime.now().isoformat(),
        )
        if self._persisted(self._manager.add(copy_profile)):
            self._refresh_list()

    def _on_load(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "Load Profile", "No profile selected.")
            return
        profile.last_used = datetime.now().isoformat()
        if not self._persisted(self._manager.update(profile)):
            return
        self._loaded_profile_id = profile.id
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
            if not self._persisted(self._manager.delete(profile.id)):
                return
            if self._loaded_profile_id == profile.id:
                self._loaded_profile_id = None
            self._refresh_list()
