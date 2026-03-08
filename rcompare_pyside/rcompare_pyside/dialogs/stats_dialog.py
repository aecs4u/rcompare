"""Diff Statistics dialog -- shows a summary of comparison results."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..utils.cli_bridge import ScanReport


class StatsDialog(QDialog):
    """Modal dialog that displays comparison statistics."""

    def __init__(self, report: ScanReport, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Comparison Statistics")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        summary = report.summary
        total = summary.total or 1  # avoid division by zero

        # Title
        title = QLabel("<b>Comparison Summary</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Grid of stats
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)

        row = 0
        stats = [
            ("Total entries:", summary.total, None),
            ("Identical:", summary.same, "#4caf50"),
            ("Different:", summary.different, "#f44336"),
            ("Left only:", summary.orphan_left, "#ff9800"),
            ("Right only:", summary.orphan_right, "#2196f3"),
            ("Unchecked:", summary.unchecked, "#9e9e9e"),
        ]

        for label_text, value, color in stats:
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(label, row, 0)

            count_label = QLabel(f"<b>{value}</b>")
            grid.addWidget(count_label, row, 1)

            if color and total > 0 and value > 0:
                pct = (value / total) * 100
                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(int(pct))
                bar.setFormat(f"{pct:.1f}%")
                bar.setTextVisible(True)
                bar.setFixedHeight(18)
                bar.setStyleSheet(
                    f"QProgressBar::chunk {{ background-color: {color}; }}"
                )
                grid.addWidget(bar, row, 2)
            elif color:
                pct_label = QLabel("0.0%")
                grid.addWidget(pct_label, row, 2)

            row += 1

        layout.addLayout(grid)

        # File counts
        layout.addSpacing(12)
        files_only = sum(
            1 for e in report.entries
            if not (e.left and e.left.is_dir) and not (e.right and e.right.is_dir)
        )
        dirs_only = summary.total - files_only
        info = QLabel(f"Files: {files_only} | Directories: {dirs_only}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        # Specialized diffs info
        specialized = []
        if report.text_diffs:
            specialized.append(f"{len(report.text_diffs)} text")
        if report.image_diffs:
            specialized.append(f"{len(report.image_diffs)} image")
        if report.csv_diffs:
            specialized.append(f"{len(report.csv_diffs)} CSV")
        if report.json_diffs:
            specialized.append(f"{len(report.json_diffs)} JSON")
        if specialized:
            spec_label = QLabel("Specialized diffs: " + ", ".join(specialized))
            spec_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(spec_label)

        # Buttons
        layout.addSpacing(8)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
