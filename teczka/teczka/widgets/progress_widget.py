"""Two-bar progress widget for comparison operations.

Shows current stage progress and overall progress with elapsed time,
modeled after Kalka's progress widget.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from teczka.hig import (
    MEDIUM_SPACING,
    PROGRESS_HEIGHT,
    PROGRESS_OVERALL_HEIGHT,
    SMALL_SPACING,
    format_count,
    format_duration,
    format_size,
)


class ProgressWidget(QWidget):
    """Two-bar progress widget with stage and overall progress."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start_time: float = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._update_elapsed)
        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SMALL_SPACING, 0, SMALL_SPACING)
        layout.setSpacing(SMALL_SPACING)

        # Row 1: stage label + elapsed time
        row1 = QHBoxLayout()
        row1.setSpacing(MEDIUM_SPACING)
        self._stage_label = QLabel("")
        self._stage_label.setStyleSheet("font-weight: bold;")
        self._elapsed_label = QLabel("")
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row1.addWidget(self._stage_label, 1)
        row1.addWidget(self._elapsed_label)
        layout.addLayout(row1)

        # Row 2: current stage progress bar
        self._stage_bar = QProgressBar()
        self._stage_bar.setFixedHeight(PROGRESS_HEIGHT)
        self._stage_bar.setRange(0, 100)
        self._stage_bar.setTextVisible(True)
        self._stage_bar.setFormat("%p%")
        layout.addWidget(self._stage_bar)

        # Row 3: detail label + step indicators
        row3 = QHBoxLayout()
        row3.setSpacing(MEDIUM_SPACING)
        self._detail_label = QLabel("")
        self._step_label = QLabel("")
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        palette = self.palette()
        muted = palette.color(palette.ColorRole.PlaceholderText)
        self._detail_label.setStyleSheet(f"color: {muted.name()};")
        self._step_label.setStyleSheet(f"color: {muted.name()};")
        row3.addWidget(self._detail_label, 1)
        row3.addWidget(self._step_label)
        layout.addLayout(row3)

        # Row 4: overall progress bar
        self._overall_bar = QProgressBar()
        self._overall_bar.setFixedHeight(PROGRESS_OVERALL_HEIGHT)
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setTextVisible(True)
        self._overall_bar.setFormat("Overall %p%")
        layout.addWidget(self._overall_bar)

    def start(self) -> None:
        """Reset and start the progress display."""
        self._start_time = time.monotonic()
        self._stage_bar.setValue(0)
        self._overall_bar.setValue(0)
        self._stage_label.setText("")
        self._detail_label.setText("")
        self._step_label.setText("")
        self._elapsed_label.setText("0s")
        self._timer.start()
        self.show()

    def stop(self) -> None:
        """Stop the elapsed timer."""
        self._timer.stop()
        self._update_elapsed()

    def reset(self) -> None:
        """Clear all progress and hide."""
        self._timer.stop()
        self._stage_bar.setValue(0)
        self._overall_bar.setValue(0)
        self._stage_label.setText("")
        self._detail_label.setText("")
        self._step_label.setText("")
        self._elapsed_label.setText("")
        self.hide()

    def update_progress(self, info: dict) -> None:
        """Update progress from a structured info dict.

        Keys: stage, stage_index, stage_count, entries_done,
              entries_total, bytes_done, bytes_total
        """
        stage = info.get("stage", "")
        stage_index = info.get("stage_index", 0)
        stage_count = max(info.get("stage_count", 1), 1)
        entries_done = info.get("entries_done", 0)
        entries_total = info.get("entries_total", 0)
        bytes_done = info.get("bytes_done", 0)
        bytes_total = info.get("bytes_total", 0)

        # Stage label: "[2/6] Comparing files..."
        self._stage_label.setText(f"[{stage_index + 1}/{stage_count}] {stage}")

        # Stage progress
        if entries_total > 0:
            stage_pct = min(int(entries_done / entries_total * 100), 99)
        else:
            stage_pct = 0
        self._stage_bar.setValue(stage_pct)

        # Overall progress
        stage_frac = stage_pct / 100.0
        overall_pct = int((stage_index + min(stage_frac, 0.99)) / stage_count * 100)
        self._overall_bar.setValue(min(overall_pct, 99))

        # Detail label
        self._detail_label.setText(self._format_detail(
            entries_done, entries_total, bytes_done, bytes_total
        ))

        # Step indicators
        self._step_label.setText(self._build_step_indicators(
            stage_index, stage_count
        ))

    def _update_elapsed(self) -> None:
        if self._start_time > 0:
            elapsed = time.monotonic() - self._start_time
            self._elapsed_label.setText(format_duration(elapsed))

    @staticmethod
    def _format_detail(
        entries_done: int,
        entries_total: int,
        bytes_done: int,
        bytes_total: int,
    ) -> str:
        parts = []
        if entries_total > 0:
            parts.append(f"{format_count(entries_done)} / ~{format_count(entries_total)} files")
        elif entries_done > 0:
            parts.append(f"{format_count(entries_done)} files")
        if bytes_total > 0:
            parts.append(f"{format_size(bytes_done)} / {format_size(bytes_total)}")
        elif bytes_done > 0:
            parts.append(format_size(bytes_done))
        return "  |  ".join(parts) if parts else ""

    @staticmethod
    def _build_step_indicators(current_index: int, total: int) -> str:
        parts = []
        for i in range(total):
            if i < current_index:
                parts.append(f"[{i + 1} done]")
            elif i == current_index:
                parts.append(f"[{i + 1} >>]")
            else:
                parts.append(f"[{i + 1}]")
        return " ".join(parts)
