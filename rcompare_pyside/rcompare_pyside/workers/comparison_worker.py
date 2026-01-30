"""Background worker for running rcompare_cli comparisons."""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal
from ..utils.cli_bridge import CliBridge, ScanReport


class ComparisonWorker(QObject):
    """Uses QProcess for non-blocking CLI invocation."""

    finished = Signal(object)  # ScanReport
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, cli_bridge: CliBridge, parent=None):
        super().__init__(parent)
        self._cli_bridge = cli_bridge
        self._process = QProcess(self)
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
        self.progress.emit("Starting comparison...")
        self._process.start(cmd[0], cmd[1:])

    def cancel(self) -> None:
        """Cancel a running comparison."""
        if self._process.state() != QProcess.NotRunning:
            self._process.kill()

    def is_running(self) -> bool:
        return self._process.state() != QProcess.NotRunning

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        stdout = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        stderr = self._process.readAllStandardError().data().decode("utf-8", errors="replace")

        if exit_status == QProcess.CrashExit:
            self.error.emit("Comparison process crashed")
            return

        if exit_code != 0:
            self.error.emit(f"Comparison failed (exit {exit_code}): {stderr.strip()}")
            return

        try:
            report = self._cli_bridge.parse_scan_report(stdout)
            self.finished.emit(report)
        except Exception as e:
            self.error.emit(f"Failed to parse results: {e}")

    def _on_stderr(self) -> None:
        data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        for line in data.strip().splitlines():
            self.progress.emit(line.strip())
