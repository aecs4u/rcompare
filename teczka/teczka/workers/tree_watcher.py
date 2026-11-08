"""Recursive local-tree change watcher with a bounded polling fallback."""

from __future__ import annotations

import os
import threading
from PySide6.QtCore import QObject, QFileSystemWatcher, QTimer, Signal

from .function_worker import FunctionWorker

_MAX_INDEXED_PATHS = 300_000
_MAX_WATCHED_PATHS = 100_000
_WATCH_BATCH_SIZE = 512


def _signature(path: str) -> tuple[int, int, int, int] | None:
    try:
        item = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return (item.st_mode, item.st_size, item.st_mtime_ns, item.st_ino)


def _collect_paths(roots: tuple[str, ...], cancel_event: threading.Event) -> dict:
    """Build a bounded list of paths and baseline metadata off the GUI thread."""
    candidates: list[tuple[str, tuple[int, int, int, int] | None]] = []
    visited_roots: set[str] = set()
    truncated = False

    for raw_root in roots:
        if cancel_event.is_set():
            break
        root = os.path.abspath(os.path.expanduser(raw_root))
        if root in visited_roots or not os.path.isdir(root):
            continue
        visited_roots.add(root)
        for current, directories, files in os.walk(root, followlinks=False):
            directories[:] = [
                name for name in directories
                if not os.path.islink(os.path.join(current, name))
            ]
            paths = [current]
            paths.extend(os.path.join(current, name) for name in files)
            for path in paths:
                if cancel_event.is_set():
                    return {"candidates": candidates, "truncated": False, "cancelled": True}
                if len(candidates) >= _MAX_INDEXED_PATHS:
                    truncated = True
                    break
                candidates.append((path, _signature(path)))
            if truncated:
                directories[:] = []
                break

    return {"candidates": candidates, "truncated": truncated, "cancelled": cancel_event.is_set()}


def _changed_paths(
    targets: tuple[tuple[str, tuple | None], ...],
    cancel_event: threading.Event,
) -> list[str]:
    """Return watched-fallback paths whose current metadata differs from baseline."""
    changes = []
    for path, old_signature in targets:
        if cancel_event.is_set():
            break
        if _signature(path) != old_signature:
            changes.append(path)
    return changes


class RecursivePathWatcher(QObject):
    """Watch files and directories recursively without blocking the GUI thread.

    Paths the platform cannot watch are checked by a single background polling
    worker. The poll runs at a fixed interval and never overlaps itself. Both
    the index and per-poll work are capped so very large trees cannot create an
    unbounded queue of filesystem work.
    """

    changed = Signal(str)
    coverage_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        max_watched_paths: int = _MAX_WATCHED_PATHS,
        poll_interval_ms: int = 2_000,
    ) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._max_watched_paths = max(0, max_watched_paths)
        self._roots: tuple[str, ...] = ()
        self._generation = 0
        self._candidates: list[tuple[str, tuple | None]] = []
        self._install_queue: list[str] = []
        self._install_failed: list[str] = []
        self._fallback_targets: tuple[tuple[str, tuple | None], ...] = ()
        self._reported_fallback_changes: set[str] = set()
        self._truncated = False
        self._index_worker: FunctionWorker | None = None
        self._poll_worker: FunctionWorker | None = None
        self._workers: set[FunctionWorker] = set()
        self._index_cancel_event: threading.Event | None = None
        self._poll_cancel_event: threading.Event | None = None
        self._poll_running = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(max(250, poll_interval_ms))
        self._poll_timer.timeout.connect(self._poll_fallback)
        self._index_timer = QTimer(self)
        self._index_timer.setSingleShot(True)
        self._index_timer.setInterval(400)
        self._index_timer.timeout.connect(self._refresh_index)

        self.watched_count = 0
        self.fallback_count = 0
        self.candidate_count = 0
        self.truncated = False

    @property
    def is_running(self) -> bool:
        return bool(
            (self._index_worker is not None and self._index_worker.isRunning())
            or self._install_queue
        )

    def start(self, roots: tuple[str, ...] | list[str]) -> None:
        """Begin indexing *roots*, replacing any prior watch set."""
        self.stop()
        self._roots = tuple(
            os.path.abspath(os.path.expanduser(path))
            for path in roots
            if path and "://" not in path
        )
        if not self._roots:
            self.coverage_changed.emit("Automatic change detection is unavailable for these sources.")
            return
        self._begin_index()

    def stop(self) -> None:
        """Stop watching the current roots and invalidate pending index results."""
        self._generation += 1
        if self._index_cancel_event is not None:
            self._index_cancel_event.set()
        if self._poll_cancel_event is not None:
            self._poll_cancel_event.set()
        self._poll_timer.stop()
        self._index_timer.stop()
        paths = self._watcher.files() + self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)
        self._roots = ()
        self._candidates = []
        self._install_queue = []
        self._fallback_targets = ()
        self._reported_fallback_changes.clear()
        self._truncated = False
        self.watched_count = 0
        self.fallback_count = 0
        self.candidate_count = 0
        self.truncated = False
        self.coverage_changed.emit("")

    def close(self) -> None:
        """Stop and wait briefly for cancellable background workers to exit."""
        self.stop()
        for worker in tuple(self._workers):
            if worker.isRunning():
                worker.wait(2_000)

    def _refresh_index(self) -> None:
        if self._roots:
            self._begin_index()

    def _begin_index(self) -> None:
        if self._index_cancel_event is not None:
            self._index_cancel_event.set()
        self._generation += 1
        generation = self._generation
        cancel_event = threading.Event()
        self._index_cancel_event = cancel_event
        worker = FunctionWorker(_collect_paths, self._roots, cancel_event, parent=self)
        worker.finished_with_result.connect(
            lambda result, token=generation: self._on_index_ready(token, result)
        )
        worker.error.connect(
            lambda message, token=generation: self._on_index_error(token, message)
        )
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda item=worker: self._workers.discard(item))
        self._workers.add(worker)
        self._index_worker = worker
        worker.start()

    def _on_index_ready(self, generation: int, result: dict) -> None:
        if generation != self._generation:
            return
        if result.get("cancelled"):
            return
        paths = self._watcher.files() + self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)

        self._candidates = result["candidates"]
        self._truncated = bool(result["truncated"])
        self.candidate_count = len(self._candidates)
        self.truncated = self._truncated
        self.watched_count = 0
        self._fallback_targets = ()
        self._reported_fallback_changes.clear()
        self._install_queue = [path for path, _ in self._candidates[: self._max_watched_paths]]
        self._install_failed: list[str] = [
            path for path, _ in self._candidates[self._max_watched_paths :]
        ]
        if not self._install_queue:
            self._finish_install(generation)
        else:
            QTimer.singleShot(0, lambda token=generation: self._install_batch(token))

    def _install_batch(self, generation: int) -> None:
        if generation != self._generation:
            return
        batch = self._install_queue[:_WATCH_BATCH_SIZE]
        del self._install_queue[:_WATCH_BATCH_SIZE]
        if batch:
            failed = self._watcher.addPaths(batch)
            self._install_failed.extend(failed)
            self.watched_count = len(self._watcher.files()) + len(self._watcher.directories())
        if self._install_queue:
            QTimer.singleShot(0, lambda token=generation: self._install_batch(token))
        else:
            self._finish_install(generation)

    def _finish_install(self, generation: int) -> None:
        if generation != self._generation:
            return
        failed_paths = set(self._install_failed)
        self._fallback_targets = tuple(
            (path, signature)
            for path, signature in self._candidates
            if path in failed_paths
        )
        self.fallback_count = len(self._fallback_targets)
        if self.fallback_count:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

        if not self.fallback_count and not self._truncated:
            message = f"Watching {self.watched_count:,} file and folder paths"
        else:
            message = (
                f"Watching {self.watched_count:,} of {self.candidate_count:,} paths; "
                f"polling {self.fallback_count:,} unwatched paths every "
                f"{self._poll_timer.interval() / 1000:g}s"
            )
            if self._truncated:
                message += "; inventory capped at 300,000 paths"
        self.coverage_changed.emit(message)

    def _on_index_error(self, generation: int, message: str) -> None:
        if generation == self._generation:
            self.error.emit(message)
            self.coverage_changed.emit("Change detection could not index these folders.")

    def _on_file_changed(self, path: str) -> None:
        self.changed.emit(path)
        if os.path.exists(path):
            self._watcher.addPath(path)

    def _on_directory_changed(self, path: str) -> None:
        self.changed.emit(path)
        self._index_timer.start()

    def _poll_fallback(self) -> None:
        if self._poll_running or not self._fallback_targets:
            return
        self._poll_running = True
        cancel_event = threading.Event()
        self._poll_cancel_event = cancel_event
        worker = FunctionWorker(
            _changed_paths, self._fallback_targets, cancel_event, parent=self
        )
        worker.finished_with_result.connect(self._on_fallback_checked)
        worker.error.connect(self.error)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: setattr(self, "_poll_running", False))
        worker.finished.connect(lambda item=worker: self._workers.discard(item))
        self._workers.add(worker)
        self._poll_worker = worker
        worker.start()

    def _on_fallback_checked(self, paths: list[str]) -> None:
        for path in paths:
            if path not in self._reported_fallback_changes:
                self._reported_fallback_changes.add(path)
                self.changed.emit(path)
