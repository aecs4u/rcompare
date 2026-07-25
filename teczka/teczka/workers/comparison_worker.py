"""Background worker for running rcompare_cli comparisons."""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal
from ..utils.cli_bridge import CliBridge, ScanReport
from ..utils.telemetry import log_error, log_exception, log_info

_PROGRESS_PREFIX = "PROGRESS:"

# Stage labels matching rcompare_core::progress::ScanStage
_STAGE_LABELS = {
    "scanning_left": "Scanning left source...",
    "scanning_right": "Scanning right source...",
    "comparing": "Comparing files...",
    "hashing": "Hashing files...",
    "diffing_files": "Running specialized diffs...",
    "saving_cache": "Saving cache...",
    "done": "Done",
}


@dataclass
class ProgressInfo:
    """Structured progress data parsed from CLI output."""

    stage: str
    stage_label: str
    stage_index: int
    stage_count: int
    entries_done: int
    entries_total: int
    percent: int


class CliJsonWorker(QObject):
    """Non-blocking QProcess wrapper for CLI subcommands that emit a single JSON report.

    Used for copy/sync (and any future one-shot command) so long-running
    operations don't block the Qt event loop the way subprocess.run does.
    """

    finished = Signal(object)  # dict parsed from JSON stdout
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = QProcess(self)
        self._stderr_buffer = ""
        self._accepted_exit_codes: tuple[int, ...] = (0,)
        self._process.finished.connect(self._on_finished)
        self._process.readyReadStandardError.connect(self._on_stderr)

    def start(self, cmd: list[str], accepted_exit_codes: tuple[int, ...] = (0,)) -> None:
        """Start the given command asynchronously."""
        self._accepted_exit_codes = accepted_exit_codes
        self._stderr_buffer = ""
        log_info(
            "starting cli json process",
            command=cmd[0] if cmd else "",
            args=cmd[1:] if len(cmd) > 1 else [],
        )
        self._process.start(cmd[0], cmd[1:])

    def cancel(self) -> None:
        if self._process.state() != QProcess.NotRunning:
            log_info("cancelling cli json process")
            self._process.kill()

    def is_running(self) -> bool:
        return self._process.state() != QProcess.NotRunning

    def _on_stderr(self) -> None:
        data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        if data:
            self._stderr_buffer += data

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        stdout = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        stderr_tail = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        if stderr_tail:
            self._stderr_buffer += stderr_tail
        stderr = self._stderr_buffer.strip()

        if exit_status == QProcess.CrashExit:
            log_error("cli json process crashed")
            self.error.emit("Process crashed")
            return

        if exit_code not in self._accepted_exit_codes:
            details = stderr or "no stderr output"
            log_error("cli json process failed", exit_code=exit_code, details=details)
            self.error.emit(f"Command failed (exit {exit_code}): {details}")
            return

        try:
            data = _json.loads(stdout)
        except Exception as e:
            log_exception("failed to decode cli json output")
            self.error.emit(f"Failed to parse result: {e}")
            return

        log_info("cli json process completed", exit_code=exit_code)
        self.finished.emit(data)


class ComparisonWorker(QObject):
    """Uses QProcess for non-blocking CLI invocation."""

    finished = Signal(object)  # ScanReport
    error = Signal(str)
    progress = Signal(str)  # Raw text progress (backward compatible)
    progress_update = Signal(object)  # ProgressInfo with structured data

    def __init__(self, cli_bridge: CliBridge, parent=None):
        super().__init__(parent)
        self._cli_bridge = cli_bridge
        self._process = QProcess(self)
        self._stderr_buffer = ""
        self._process.finished.connect(self._on_finished)
        self._process.readyReadStandardError.connect(self._on_stderr)

    def start_scan(
        self,
        left: str,
        right: str,
        follow_symlinks: bool = False,
        verify_hashes: bool = False,
        ignore_patterns: list[str] | None = None,
        text_diff: bool = False,
        image_diff: bool = False,
        image_exif: bool = False,
        image_tolerance: int = 1,
        csv_diff: bool = False,
        excel_diff: bool = False,
        json_diff: bool = False,
        yaml_diff: bool = False,
        parquet_diff: bool = False,
        ignore_whitespace: str | None = None,
        ignore_case: bool = False,
    ) -> None:
        """Start an async folder scan."""
        args = ["scan", left, right, "--json"]
        if follow_symlinks:
            args.append("--follow-symlinks")
        if verify_hashes:
            args.append("--verify-hashes")
        for p in ignore_patterns or []:
            args.extend(["--ignore", p])
        if text_diff:
            args.append("--text-diff")
        if image_diff:
            args.append("--image-diff")
        if image_exif:
            args.append("--image-exif")
        if image_tolerance != 1:
            args.extend(["--image-tolerance", str(image_tolerance)])
        if csv_diff:
            args.append("--csv-diff")
        if excel_diff:
            args.append("--excel-diff")
        if json_diff:
            args.append("--json-diff")
        if yaml_diff:
            args.append("--yaml-diff")
        if parquet_diff:
            args.append("--parquet-diff")
        if ignore_whitespace:
            args.extend(["--ignore-whitespace", ignore_whitespace])
        if ignore_case:
            args.append("--ignore-case")

        cmd = self._cli_bridge.build_command(args)
        self._stderr_buffer = ""
        log_info(
            "starting async scan process",
            command=cmd[0] if cmd else "",
            args=cmd[1:] if len(cmd) > 1 else [],
        )
        self.progress.emit("Starting comparison...")
        self._process.start(cmd[0], cmd[1:])

    def cancel(self) -> None:
        """Cancel a running comparison."""
        if self._process.state() != QProcess.NotRunning:
            log_info("cancelling comparison process")
            self._process.kill()

    def is_running(self) -> bool:
        return self._process.state() != QProcess.NotRunning

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        stdout = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        stderr_tail = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        if stderr_tail:
            self._stderr_buffer += stderr_tail
        stderr = self._stderr_buffer.strip()

        if exit_status == QProcess.CrashExit:
            log_error("comparison process crashed")
            self.error.emit("Comparison process crashed")
            return

        # rcompare_cli exit codes:
        #   0 => no differences found
        #   2 => differences found (successful comparison)
        if exit_code not in (0, 2):
            # Filter out PROGRESS: lines from error display
            details_lines = [
                line for line in (stderr or "no stderr output").splitlines()
                if not line.startswith(_PROGRESS_PREFIX)
            ]
            details = "\n".join(details_lines) or "no stderr output"
            log_error("comparison process failed", exit_code=exit_code, details=details)
            self.error.emit(f"Comparison failed (exit {exit_code}): {details}")
            return

        try:
            report = self._cli_bridge.parse_scan_report(stdout)
            log_info(
                "comparison process completed",
                exit_code=exit_code,
                entries=len(report.entries),
                different=report.summary.different,
            )
            self.finished.emit(report)
        except Exception as e:
            log_exception("failed to parse comparison result")
            self.error.emit(f"Failed to parse results: {e}")

    def _on_stderr(self) -> None:
        data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        if not data:
            return
        self._stderr_buffer += data
        for line in data.strip().splitlines():
            stripped = line.strip()
            if stripped.startswith(_PROGRESS_PREFIX):
                self._parse_progress_line(stripped)
            else:
                self.progress.emit(stripped)

    def _parse_progress_line(self, line: str) -> None:
        """Parse a structured PROGRESS:{json} line from the CLI."""
        try:
            raw = line[len(_PROGRESS_PREFIX):]
            obj = _json.loads(raw)
            stage = obj.get("stage", "")
            entries_done = int(obj.get("entries_done", 0))
            entries_total = int(obj.get("entries_total", 0))
            percent = 0
            if entries_total > 0:
                percent = min(100, int(entries_done / entries_total * 100))

            info = ProgressInfo(
                stage=stage,
                stage_label=_STAGE_LABELS.get(stage, stage),
                stage_index=int(obj.get("stage_index", 0)),
                stage_count=int(obj.get("stage_count", 6)),
                entries_done=entries_done,
                entries_total=entries_total,
                percent=percent,
            )
            self.progress_update.emit(info)

            # Also emit a human-readable text for backward compatibility
            if entries_total > 0:
                self.progress.emit(
                    f"{info.stage_label} ({entries_done}/{entries_total}, {percent}%)"
                )
            else:
                self.progress.emit(info.stage_label)
        except (ValueError, KeyError, _json.JSONDecodeError):
            # Malformed progress line — emit as raw text
            self.progress.emit(line)
