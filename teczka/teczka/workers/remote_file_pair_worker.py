"""Asynchronously stage a selected remote file pair through rcompare_cli."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QObject, QProcess, Signal

from ..utils.cli_bridge import unwrap_json_envelope
from ..utils.source_paths import is_remote_source, source_log_label, source_scheme


@dataclass
class StagedRemoteFilePair:
    """Local copies of a pair plus the directory that owns their lifetime."""

    left_path: Path
    right_path: Path
    temporary_directory: tempfile.TemporaryDirectory


def _safe_relative_file_name(relative_path: str) -> tuple[str, str]:
    """Return a normalized relative path and leaf name, rejecting traversal."""
    normalized = relative_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part == ".." for part in path.parts)
        or not path.name
    ):
        raise ValueError("The selected path is not a safe relative file path.")
    return path.as_posix(), path.name


class RemoteFilePairWorker(QObject):
    """Read both sides using the CLI without blocking Qt's event loop.

    Each ``read`` writes to a private temporary directory. The completed
    result transfers ownership of that directory to the caller so the files
    can remain available while the selected viewer loads them.
    """

    completed = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        cli_path: str,
        left_root: str,
        right_root: str,
        relative_path: str | tuple[str, str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._cli_path = cli_path
        self._left_root = left_root
        self._right_root = right_root
        raw_paths = (
            (relative_path, relative_path)
            if isinstance(relative_path, str)
            else relative_path
        )
        if len(raw_paths) != 2:
            raise ValueError("A file pair requires one relative path for each side.")
        self._relative_paths = tuple(
            _safe_relative_file_name(path)[0] for path in raw_paths
        )
        leaf_names = tuple(_safe_relative_file_name(path)[1] for path in raw_paths)
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="teczka-remote-pair-"
        )
        stage_root = Path(self._temporary_directory.name)
        self._outputs = (
            stage_root / "left" / leaf_names[0],
            stage_root / "right" / leaf_names[1],
        )
        self._sides = ("left", "right")
        self._side_index = 0
        self._required_schemes = {
            scheme
            for root in (left_root, right_root)
            if is_remote_source(root) and (scheme := source_scheme(root))
        }
        self._checking_capabilities = False
        self._stderr = ""
        self._cancelled = False
        self._terminal = False

        self._process = QProcess(self)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)

    def start(self) -> None:
        """Check source support, then read the left and right files."""
        if self._required_schemes:
            self._checking_capabilities = True
            self._stderr = ""
            self._process.start(self._cli_path, ["capabilities", "--json"])
            return
        self._start_side()

    def cancel(self) -> None:
        """Stop the active CLI read and release temporary files."""
        if self._terminal:
            return
        self._cancelled = True
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1_000)
        if not self._terminal:
            self._temporary_directory.cleanup()
            self._terminal = True
            self.finished.emit()

    def _start_side(self) -> None:
        side = self._sides[self._side_index]
        output_path = self._outputs[self._side_index]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr = ""
        arguments = [
            "read",
            "--side",
            side,
            "--path",
            self._relative_paths[self._side_index],
            self._left_root,
            self._right_root,
            "--out",
            str(output_path),
        ]
        self._process.start(self._cli_path, arguments)

    def _read_stderr(self) -> None:
        self._stderr += bytes(self._process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )

    def _on_process_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        if self._terminal:
            return
        if self._cancelled:
            self._finish_cancelled()
            return

        self._read_stderr()
        stdout = bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        if self._checking_capabilities:
            self._on_capabilities_finished(stdout, exit_code, exit_status)
            return
        if exit_status == QProcess.ExitStatus.CrashExit:
            self._finish_error("rcompare_cli crashed while reading a remote file.")
            return
        if exit_code != 0:
            details = self._stderr.strip() or (
                f"rcompare_cli exited with code {exit_code}."
            )
            self._finish_error(self._redact_sources(details))
            return

        self._side_index += 1
        if self._side_index < len(self._sides):
            self._start_side()
            return

        self._terminal = True
        self.completed.emit(
            StagedRemoteFilePair(
                self._outputs[0],
                self._outputs[1],
                self._temporary_directory,
            )
        )
        self.finished.emit()

    def _on_capabilities_finished(
        self,
        stdout: str,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self._checking_capabilities = False
        if exit_status == QProcess.ExitStatus.CrashExit or exit_code != 0:
            details = self._stderr.strip() or "no diagnostic output"
            self._finish_error(
                "Unable to check remote-source support: "
                f"{self._redact_sources(details)}"
            )
            return
        try:
            decoded = json.loads(stdout)
            report = (
                unwrap_json_envelope(decoded) if isinstance(decoded, dict) else None
            )
        except (json.JSONDecodeError, TypeError):
            report = None
        advertised = report.get("source_schemes") if isinstance(report, dict) else None
        if not isinstance(advertised, list) or not all(
            isinstance(scheme, str) for scheme in advertised
        ):
            self._finish_error(
                "Remote file comparison needs an rcompare_cli build that reports "
                "source_schemes in `capabilities --json`. Update the configured CLI."
            )
            return
        missing = sorted(self._required_schemes - {item.lower() for item in advertised})
        if missing:
            self._finish_error(
                "The configured rcompare_cli does not support remote scheme(s): "
                + ", ".join(missing)
            )
            return
        self._start_side()

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if self._terminal or self._cancelled:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._finish_error(
                "Unable to start the configured rcompare_cli: "
                f"{self._process.errorString()}"
            )

    def _redact_sources(self, message: str) -> str:
        for source in (self._left_root, self._right_root):
            if source:
                message = message.replace(source, source_log_label(source))
        return message

    def _finish_error(self, message: str) -> None:
        if self._terminal:
            return
        self._terminal = True
        self._temporary_directory.cleanup()
        self.error.emit(message)
        self.finished.emit()

    def _finish_cancelled(self) -> None:
        if self._terminal:
            return
        self._terminal = True
        self._temporary_directory.cleanup()
        self.finished.emit()
