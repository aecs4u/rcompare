from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MAX_HISTORY = 50


@dataclass
class Operation:
    """Represents a single reversible file operation."""

    op_type: str  # "copy", "delete", "rename", "move"
    source_path: str
    dest_path: str
    backup_path: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OperationHistory:
    """Undo/redo stack for file operations.

    Maintains a linear history of operations with a pointer that tracks
    the current position. Pushing a new operation after an undo discards
    any redo history beyond the current pointer.
    """

    def __init__(self) -> None:
        self._operations: list[Operation] = []
        self._pointer: int = -1
        self._backup_dir: Optional[Path] = None

    # -- public API ----------------------------------------------------------

    def push(self, op: Operation) -> None:
        """Record a new operation, discarding any redo history."""
        # Trim redo entries beyond the current pointer
        self._operations = self._operations[: self._pointer + 1]
        self._operations.append(op)

        # Enforce maximum history size
        if len(self._operations) > MAX_HISTORY:
            self._operations = self._operations[-MAX_HISTORY:]

        self._pointer = len(self._operations) - 1

    def undo(self) -> Optional[Operation]:
        """Return the operation to undo, or *None* if nothing to undo."""
        if not self.can_undo:
            return None
        op = self._operations[self._pointer]
        self._pointer -= 1
        return op

    def redo(self) -> Optional[Operation]:
        """Return the operation to redo, or *None* if nothing to redo."""
        if not self.can_redo:
            return None
        self._pointer += 1
        return self._operations[self._pointer]

    def clear(self) -> None:
        """Reset all history."""
        self._operations.clear()
        self._pointer = -1

    # -- properties ----------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return self._pointer >= 0

    @property
    def can_redo(self) -> bool:
        return self._pointer < len(self._operations) - 1

    @property
    def last_op(self) -> Optional[Operation]:
        """Return the most recent operation without moving the pointer."""
        if self._pointer < 0:
            return None
        return self._operations[self._pointer]

    @property
    def backup_dir(self) -> Path:
        """Return (and lazily create) a temporary directory for backups."""
        if self._backup_dir is None or not self._backup_dir.exists():
            self._backup_dir = Path(tempfile.mkdtemp(prefix="rcompare_backup_"))
        return self._backup_dir


# -- helper functions --------------------------------------------------------


def create_backup(source: Path, backup_dir: Path) -> Path:
    """Copy *source* (file or directory) into *backup_dir* with a unique name.

    Returns the path to the backup copy.
    """
    unique_name = f"{source.name}_{uuid.uuid4().hex[:8]}"
    backup_path = backup_dir / unique_name

    if source.is_dir():
        shutil.copytree(source, backup_path)
    else:
        shutil.copy2(source, backup_path)

    return backup_path


def restore_backup(backup_path: Path, target: Path) -> None:
    """Restore a previously created backup to *target*.

    If *target* already exists it is removed first.
    """
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    if backup_path.is_dir():
        shutil.copytree(backup_path, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, target)
