"""Side-by-side filesystem properties for a compared folder item."""

from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _identity_name(identifier: int, resolver: Callable[[int], object]) -> str:
    try:
        record = resolver(identifier)
    except (KeyError, OSError):
        return str(identifier)
    return str(getattr(record, "pw_name", getattr(record, "gr_name", identifier)))


def _format_time(timestamp: float) -> str:
    try:
        value = datetime.fromtimestamp(timestamp).astimezone()
    except (OverflowError, OSError, ValueError):
        return "Unavailable"
    return value.strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def _file_type(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "Symbolic link"
    if stat.S_ISDIR(mode):
        return "Folder"
    if stat.S_ISREG(mode):
        return "File"
    if stat.S_ISFIFO(mode):
        return "FIFO"
    if stat.S_ISSOCK(mode):
        return "Socket"
    if stat.S_ISCHR(mode):
        return "Character device"
    if stat.S_ISBLK(mode):
        return "Block device"
    return "Unknown"


def _property_rows(path: Path) -> list[tuple[str, str]]:
    """Return readable lstat-based properties; never follow a symlink."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return [("Availability", "Missing on this side")]
    except OSError as exc:
        return [("Availability", f"Unavailable: {exc}")]

    mode = metadata.st_mode
    rows = [
        ("Availability", "Present"),
        ("Path", str(path)),
        ("Type", _file_type(mode)),
    ]

    if not stat.S_ISDIR(mode):
        rows.append(("Size", f"{metadata.st_size:,} bytes"))

    rows.append(("Permissions", stat.filemode(mode)))

    uid = getattr(metadata, "st_uid", None)
    gid = getattr(metadata, "st_gid", None)
    if uid is not None:
        try:
            import pwd

            owner = _identity_name(uid, pwd.getpwuid)
        except ImportError:
            owner = str(uid)
        rows.append(("Owner", owner))
    if gid is not None:
        try:
            import grp

            group = _identity_name(gid, grp.getgrgid)
        except ImportError:
            group = str(gid)
        rows.append(("Group", group))

    rows.extend(
        [
            ("Modified", _format_time(metadata.st_mtime)),
            ("Accessed", _format_time(metadata.st_atime)),
        ]
    )
    if hasattr(metadata, "st_birthtime"):
        rows.append(("Created", _format_time(metadata.st_birthtime)))
    elif os.name == "nt":
        rows.append(("Created", _format_time(metadata.st_ctime)))
    else:
        rows.append(("Metadata changed", _format_time(metadata.st_ctime)))

    if stat.S_ISLNK(mode):
        try:
            target = os.readlink(path)
        except OSError as exc:
            target = f"Unavailable: {exc}"
        rows.append(("Link target", target))

    return rows


class PropertiesDialog(QDialog):
    """Show the selected relative path on both sides of the comparison."""

    def __init__(
        self,
        relative_path: str,
        left_path: Path,
        right_path: Path,
        parent: QWidget | None = None,
        *,
        selected_side: str = "left",
    ) -> None:
        super().__init__(parent)
        self._left_path = left_path
        self._right_path = right_path
        self._value_labels: dict[str, QLabel] = {}

        self.setWindowTitle(f"Properties — {relative_path}")
        self.setMinimumSize(760, 420)

        layout = QVBoxLayout(self)
        heading = QLabel(relative_path)
        heading.setObjectName("propertiesRelativePath")
        heading.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        sides = QHBoxLayout()
        left_title = "LHS (selected)" if selected_side == "left" else "LHS"
        right_title = "RHS (selected)" if selected_side == "right" else "RHS"
        sides.addWidget(self._build_side(left_title, "left", left_path), 1)
        sides.addWidget(self._build_side(right_title, "right", right_path), 1)
        layout.addLayout(sides, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_side(self, title: str, side: str, path: Path) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        form = QFormLayout()

        for label, value in _property_rows(path):
            key = label.lower().replace(" ", "_")
            value_label = QLabel(value)
            value_label.setObjectName(f"propertyValue_{side}_{key}")
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            value_label.setWordWrap(True)
            self._value_labels[f"{side}.{key}"] = value_label
            form.addRow(f"{label}:", value_label)

        layout.addLayout(form)

        copy_button = QPushButton("Copy path")
        copy_button.setObjectName(f"propertiesCopyPath_{side}")
        copy_button.setEnabled(path.exists() or path.is_symlink())
        copy_button.clicked.connect(lambda: self.copy_path(path))
        layout.addWidget(copy_button)

        return group

    @staticmethod
    def copy_path(path: Path) -> None:
        QApplication.clipboard().setText(str(path))
