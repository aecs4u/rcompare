"""Background worker for running rcompare_cli comparisons."""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Optional
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from ..models.comparison import (
    IncrementalTreeBuilder,
    TreeNode,
    build_tree_with_options,
)
from ..utils.cli_bridge import CliBridge, ScanReport, ScanSummary
from ..utils.telemetry import log_error, log_info
from .function_worker import FunctionWorker

_PROGRESS_PREFIX = "PROGRESS:"

# Reported on results assembled from --jsonl lines. The per-line summary is
# schema-checked as it arrives (CliBridge.parse_summary_obj), so this records
# how the report was built rather than re-deriving a version.
SCHEMA_VERSION_STREAMED = "1.1.0"


def _empty_summary(total: int) -> ScanSummary:
    """Fallback when the CLI exits before emitting its summary line."""
    return ScanSummary(
        total=total, same=0, different=0,
        orphan_left=0, orphan_right=0, unchecked=0,
    )

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


@dataclass
class PartialResult:
    """A snapshot of a comparison that is still running.

    Emitted repeatedly while --jsonl output streams in, so the folder view can
    fill progressively instead of staying empty until the scan completes.
    """

    summary: Optional[ScanSummary]
    tree: TreeNode
    entries_seen: int


@dataclass
class ComparisonResult:
    """Parsed report and pre-built tree produced outside the GUI thread."""

    report: ScanReport
    tree: TreeNode


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
        self._result_worker: FunctionWorker | None = None
        self._cancelled = False
        self._process.finished.connect(self._on_finished)
        self._process.readyReadStandardError.connect(self._on_stderr)

    def start(self, cmd: list[str], accepted_exit_codes: tuple[int, ...] = (0,)) -> None:
        """Start the given command asynchronously."""
        self._accepted_exit_codes = accepted_exit_codes
        self._stderr_buffer = ""
        self._cancelled = False
        log_info(
            "starting cli json process",
            command=cmd[0] if cmd else "",
            args=cmd[1:] if len(cmd) > 1 else [],
        )
        self._process.start(cmd[0], cmd[1:])

    def cancel(self) -> None:
        self._cancelled = True
        if self._result_worker is not None:
            self._result_worker.cancel()
        if self._process.state() != QProcess.NotRunning:
            log_info("cancelling cli json process")
            self._process.kill()

    def is_running(self) -> bool:
        return self._process.state() != QProcess.NotRunning or (
            self._result_worker is not None and self._result_worker.isRunning()
        )

    def _on_stderr(self) -> None:
        data = bytes(self._process.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
        if data:
            self._stderr_buffer += data

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        stdout = bytes(self._process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        stderr_tail = bytes(self._process.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
        if stderr_tail:
            self._stderr_buffer += stderr_tail
        stderr = self._stderr_buffer.strip()

        if self._cancelled:
            return
        if exit_status == QProcess.CrashExit:
            log_error("cli json process crashed")
            self.error.emit("Process crashed")
            return

        if exit_code not in self._accepted_exit_codes:
            details = stderr or "no stderr output"
            log_error("cli json process failed", exit_code=exit_code, details=details)
            self.error.emit(f"Command failed (exit {exit_code}): {details}")
            return

        self._result_worker = FunctionWorker(_json.loads, stdout, parent=self)
        self._result_worker.finished_with_result.connect(
            lambda data: self._on_json_ready(data, exit_code)
        )
        self._result_worker.error.connect(self._on_json_error)
        self._result_worker.start()

    def _on_json_ready(self, data: dict, exit_code: int) -> None:
        if self._cancelled:
            self._result_worker = None
            return
        log_info("cli json process completed", exit_code=exit_code)
        self.finished.emit(data)
        self._result_worker = None

    def _on_json_error(self, message: str) -> None:
        if self._cancelled:
            self._result_worker = None
            return
        log_error("failed to decode cli json output", details=message)
        self.error.emit(f"Failed to parse result: {message}")
        self._result_worker = None


class ComparisonWorker(QObject):
    """Uses QProcess for non-blocking CLI invocation."""

    finished = Signal(object)  # ScanReport
    error = Signal(str)
    progress = Signal(str)  # Raw text progress (backward compatible)
    progress_update = Signal(object)  # ProgressInfo with structured data
    partial_ready = Signal(object)  # PartialResult while the scan is running

    # Cap on entry lines decoded per event-loop pass. Decoding costs roughly
    # 4us/entry, so this bounds each pass to a few milliseconds and keeps the
    # UI interactive no matter how fast the CLI floods stdout.
    _MAX_LINES_PER_PASS = 2000
    # How often a partial tree is published to the view while streaming, and
    # the ceiling that back-off may raise it to on very large result sets.
    _PUBLISH_INTERVAL_MS = 400
    _MAX_PUBLISH_INTERVAL_MS = 5000

    def __init__(self, cli_bridge: CliBridge, parent=None):
        super().__init__(parent)
        self._cli_bridge = cli_bridge
        self._process = QProcess(self)
        self._stderr_buffer = ""
        self._stdout_remainder = ""
        self._result_worker: FunctionWorker | None = None
        self._folder_view_mode = "compare_structure"
        self._always_show_folders = True
        self._cancelled = False
        self._streaming = False
        self._builder: IncrementalTreeBuilder | None = None
        self._entries: list = []
        self._summary: ScanSummary | None = None
        self._dirty = False
        self._process.finished.connect(self._on_finished)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.readyReadStandardOutput.connect(self._on_stdout)

        self._publish_timer = QTimer(self)
        self._publish_timer.setInterval(self._PUBLISH_INTERVAL_MS)
        self._publish_timer.timeout.connect(self._publish_partial)

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
        regex_rules: list[str] | None = None,
        csv_key_columns: list[str] | None = None,
        cache_dir: str | None = None,
        folder_view_mode: str = "compare_structure",
        always_show_folders: bool = True,
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
        for rule in regex_rules or []:
            args.extend(["--regex-rule", rule])
        for column in csv_key_columns or []:
            args.extend(["--csv-key", column])
        if cache_dir:
            args.extend(["--cache-dir", cache_dir])

        # --jsonl emits one summary line followed by one line per entry, so
        # results can be rendered while the scan is still running instead of
        # after it. Only the default hierarchical mode can be built
        # incrementally; the other modes need the full entry set up front.
        #
        # The CLI rejects --json together with --jsonl, so swap rather than add.
        # --jsonl is newer than the oldest binaries teczka may be pointed at, so
        # it is feature-detected rather than assumed; older builds keep the
        # previous all-at-once behaviour instead of failing.
        self._streaming = folder_view_mode in (
            "", "compare_structure"
        ) and self._cli_bridge.supports_flag("scan", "--jsonl")
        if self._streaming:
            args = ["--jsonl" if a == "--json" else a for a in args]

        cmd = self._cli_bridge.build_command(args)
        self._stderr_buffer = ""
        self._stdout_remainder = ""
        self._cancelled = False
        self._folder_view_mode = folder_view_mode
        self._always_show_folders = always_show_folders
        self._builder = IncrementalTreeBuilder() if self._streaming else None
        self._entries = []
        self._summary = None
        self._dirty = False
        self._left = left
        self._right = right
        if self._streaming:
            self._publish_timer.start()
        log_info(
            "starting async scan process",
            command=cmd[0] if cmd else "",
            args=cmd[1:] if len(cmd) > 1 else [],
        )
        self.progress.emit("Starting comparison...")
        self._process.start(cmd[0], cmd[1:])

    def cancel(self) -> None:
        """Cancel a running comparison."""
        self._cancelled = True
        self._publish_timer.stop()
        if self._result_worker is not None:
            self._result_worker.cancel()
        if self._process.state() != QProcess.NotRunning:
            log_info("cancelling comparison process")
            self._process.kill()

    def is_running(self) -> bool:
        return self._process.state() != QProcess.NotRunning or (
            self._result_worker is not None and self._result_worker.isRunning()
        )

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        stdout = bytes(self._process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        stderr_tail = bytes(self._process.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
        if stderr_tail:
            self._stderr_buffer += stderr_tail
        stderr = self._stderr_buffer.strip()

        if self._cancelled:
            return
        if exit_status == QProcess.CrashExit:
            log_error("comparison process crashed")
            self.error.emit("Comparison process crashed")
            return
        if self._streaming:
            # Drain anything that arrived between the last readyRead and exit.
            self._on_stdout()
            if self._stdout_remainder.strip():
                self._consume_lines([self._stdout_remainder])
                self._stdout_remainder = ""

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

        # clap also exits 2 on a usage error, which is indistinguishable from
        # "differences found" by exit code alone. Without this, a malformed
        # invocation is reported to the user as a successful empty comparison.
        if not self._summary and not self._entries and stdout.strip() == "":
            details = "\n".join(
                line for line in stderr.splitlines()
                if not line.startswith(_PROGRESS_PREFIX)
            ).strip()
            if details:
                log_error("comparison produced no output", exit_code=exit_code,
                          details=details)
                self.error.emit(f"Comparison produced no output: {details}")
                return

        if self._streaming:
            # Everything was decoded incrementally as it arrived; the tree only
            # needs its final aggregate/sort pass. No second parse, no second
            # copy of the result set.
            report = ScanReport(
                schema_version=SCHEMA_VERSION_STREAMED,
                left=self._left,
                right=self._right,
                summary=self._summary or _empty_summary(len(self._entries)),
                entries=self._entries,
            )
            if self._builder is None:
                self.error.emit("Streaming comparison ended without a tree builder")
                return
            result = ComparisonResult(report=report, tree=self._builder.finish())
            self._on_result_ready(result, exit_code)
            return

        # JSON decoding and tree construction scale with the complete result
        # set, so keep both away from the Qt event loop.
        self._result_worker = FunctionWorker(
            self._parse_report_and_tree,
            stdout,
            self._folder_view_mode,
            self._always_show_folders,
            parent=self,
        )
        self._result_worker.finished_with_result.connect(
            lambda result: self._on_result_ready(result, exit_code)
        )
        self._result_worker.error.connect(self._on_result_error)
        self._result_worker.start()

    def _parse_report_and_tree(
        self, stdout: str, folder_view_mode: str, always_show_folders: bool
    ) -> ComparisonResult:
        report = self._cli_bridge.parse_scan_report(stdout)
        tree = build_tree_with_options(
            report,
            folder_view_mode,
            always_show_folders=always_show_folders,
        )
        return ComparisonResult(report=report, tree=tree)

    def _on_result_ready(self, result: ComparisonResult, exit_code: int) -> None:
        if self._cancelled:
            self._result_worker = None
            return
        log_info(
            "comparison process completed",
            exit_code=exit_code,
            entries=len(result.report.entries),
            different=result.report.summary.different,
        )
        self.finished.emit(result)
        self._result_worker = None

    def _on_result_error(self, message: str) -> None:
        if self._cancelled:
            self._result_worker = None
            return
        log_error("failed to parse comparison result", details=message)
        self.error.emit(f"Failed to parse results: {message}")
        self._result_worker = None

    def _on_stdout(self) -> None:
        """Decode newly arrived --jsonl lines without blocking the event loop.

        Non-streaming runs leave the data in the QProcess buffer for
        _on_finished to read in one go, exactly as before.
        """
        if not self._streaming or self._cancelled:
            return
        data = bytes(self._process.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        if not data:
            return
        self._stdout_remainder += data
        # Keep the trailing fragment: the pipe may have been read mid-line.
        lines = self._stdout_remainder.split("\n")
        self._stdout_remainder = lines.pop()
        self._consume_lines(lines)

    def _consume_lines(self, lines: list[str]) -> None:
        """Decode up to _MAX_LINES_PER_PASS lines, yielding between batches."""
        batch = lines[: self._MAX_LINES_PER_PASS]
        rest = lines[self._MAX_LINES_PER_PASS:]
        for line in batch:
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
            except ValueError:
                continue
            kind = obj.get("type")
            if kind == "entry":
                try:
                    entry = self._cli_bridge.parse_entry_obj(obj)
                except (KeyError, ValueError):
                    continue
                self._entries.append(entry)
                if self._builder is not None:
                    self._builder.add(entry)
                self._dirty = True
            elif kind == "summary":
                # Arrives first: totals are known before any entry renders.
                self._summary = self._cli_bridge.parse_summary_obj(obj)
                self._dirty = True
        if rest and not self._cancelled:
            # Hand control back to the event loop before decoding the rest.
            QTimer.singleShot(0, lambda: self._consume_lines(rest))

    def _publish_partial(self) -> None:
        """Push the tree built so far to the view, if anything changed."""
        if not self._streaming or self._cancelled or not self._dirty:
            return
        if self._builder is None:
            return
        self._dirty = False
        seen = len(self._builder)
        self.partial_ready.emit(
            PartialResult(
                summary=self._summary,
                tree=self._builder.snapshot(),
                entries_seen=seen,
            )
        )
        # Snapshotting copies the tree, so its cost grows with the result set.
        # Back the interval off as the tree grows to keep that overhead a
        # roughly fixed share of runtime instead of letting it dominate on
        # very large comparisons.
        self._publish_timer.setInterval(
            min(self._MAX_PUBLISH_INTERVAL_MS,
                max(self._PUBLISH_INTERVAL_MS, seen // 20))
        )

    def _on_stderr(self) -> None:
        data = bytes(self._process.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
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

            # Also emit a human-readable text for backward compatibility.
            # During the directory walk the total is not yet known, but the
            # running count still distinguishes a slow scan from a hung one —
            # which is the whole point of reporting it.
            if entries_total > 0:
                self.progress.emit(
                    f"{info.stage_label} ({entries_done:,}/{entries_total:,}, {percent}%)"
                )
            elif entries_done > 0:
                self.progress.emit(f"{info.stage_label} ({entries_done:,} entries)")
            else:
                self.progress.emit(info.stage_label)
        except (ValueError, KeyError, _json.JSONDecodeError):
            # Malformed progress line — emit as raw text
            self.progress.emit(line)
