"""Image comparison view with pixel-level statistics."""

from __future__ import annotations

import os
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GREEN = QColor("#2e7d32")
_YELLOW = QColor("#f9a825")
_RED = QColor("#c62828")


def _similarity_color(similarity_pct: float) -> QColor:
    """Return a colour representing the similarity percentage."""
    if similarity_pct > 99.0:
        return _GREEN
    if similarity_pct > 95.0:
        return _YELLOW
    return _RED


# ---------------------------------------------------------------------------
# ZoomableGraphicsView
# ---------------------------------------------------------------------------


class ZoomableGraphicsView(QGraphicsView):
    """QGraphicsView subclass that supports Ctrl+Mouse-wheel zoom."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def fit_to_view(self) -> None:
        """Scale the scene so the full image fits within the viewport."""
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)


# ---------------------------------------------------------------------------
# ImageView
# ---------------------------------------------------------------------------


class ImageView(QWidget):
    """Side-by-side image comparison widget with pixel statistics.

    Two :class:`QGraphicsView` panels display images loaded from file paths.
    A statistics panel at the bottom shows pixel-level comparison metrics
    computed via Pillow when available.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Left panel ---------------------------------------------------
        self._left_path_label = QLabel("(no image loaded)")
        self._left_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._left_browse_btn = QPushButton("Browse...")
        self._left_browse_btn.clicked.connect(self._browse_left)
        self._left_fit_btn = QPushButton("Fit")
        self._left_fit_btn.setToolTip("Fit image to view")
        self._left_scene = QGraphicsScene(self)
        self._left_view = ZoomableGraphicsView(self)
        self._left_view.setScene(self._left_scene)

        left_header = QHBoxLayout()
        left_header.addWidget(self._left_path_label, stretch=1)
        left_header.addWidget(self._left_fit_btn)
        left_header.addWidget(self._left_browse_btn)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(left_header)
        left_layout.addWidget(self._left_view)

        # Right panel --------------------------------------------------
        self._right_path_label = QLabel("(no image loaded)")
        self._right_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._right_browse_btn = QPushButton("Browse...")
        self._right_browse_btn.clicked.connect(self._browse_right)
        self._right_fit_btn = QPushButton("Fit")
        self._right_fit_btn.setToolTip("Fit image to view")
        self._right_scene = QGraphicsScene(self)
        self._right_view = ZoomableGraphicsView(self)
        self._right_view.setScene(self._right_scene)

        right_header = QHBoxLayout()
        right_header.addWidget(self._right_path_label, stretch=1)
        right_header.addWidget(self._right_fit_btn)
        right_header.addWidget(self._right_browse_btn)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(right_header)
        right_layout.addWidget(self._right_view)

        # Fit buttons --------------------------------------------------
        self._left_fit_btn.clicked.connect(self._left_view.fit_to_view)
        self._right_fit_btn.clicked.connect(self._right_view.fit_to_view)

        # Splitter for images ------------------------------------------
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        # Stats panel --------------------------------------------------
        self._stats_box = QGroupBox("Comparison Statistics")
        stats_layout = QHBoxLayout(self._stats_box)

        self._lbl_left_dims = QLabel("Left: -")
        self._lbl_right_dims = QLabel("Right: -")
        self._lbl_total_pixels = QLabel("Total pixels: -")
        self._lbl_diff_pixels = QLabel("Different pixels: -")
        self._lbl_diff_pct = QLabel("Difference: -")
        self._lbl_mean_diff = QLabel("Mean diff: -")
        self._lbl_similarity = QLabel("Similarity: -")

        for lbl in (
            self._lbl_left_dims,
            self._lbl_right_dims,
            self._lbl_total_pixels,
            self._lbl_diff_pixels,
            self._lbl_diff_pct,
            self._lbl_mean_diff,
            self._lbl_similarity,
        ):
            stats_layout.addWidget(lbl)

        # Error label (hidden by default) ------------------------------
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red; font-weight: bold;")
        self._error_label.setVisible(False)

        # Main layout --------------------------------------------------
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(QLabel("<b>Image Compare</b>"))
        main_layout.addWidget(self._error_label)
        main_layout.addWidget(splitter, stretch=1)
        main_layout.addWidget(self._stats_box)

        # Internal state -----------------------------------------------
        self._left_path: str = ""
        self._right_path: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compare_images(self, left_path: str, right_path: str) -> None:
        """Load two images, display them, and compute pixel statistics."""
        self._error_label.setVisible(False)
        self._left_path = left_path
        self._right_path = right_path

        left_ok = self._load_image(left_path, self._left_scene, self._left_path_label)
        right_ok = self._load_image(right_path, self._right_scene, self._right_path_label)

        if not left_ok or not right_ok:
            problems: list[str] = []
            if not left_ok:
                problems.append(f"Cannot read left image: {left_path}")
            if not right_ok:
                problems.append(f"Cannot read right image: {right_path}")
            self._show_error("; ".join(problems))
            self._clear_stats()
            return

        self._compute_stats(left_path, right_path)

    def load_from_cli_report(self, report_dict: dict[str, Any]) -> None:
        """Populate the view from a CLI JSON report dictionary.

        Expected keys (all optional):
            left_path, right_path, left_width, left_height,
            right_width, right_height, total_pixels, different_pixels,
            difference_pct, mean_diff, similarity_pct
        """
        self._error_label.setVisible(False)

        left_path = report_dict.get("left_path", "")
        right_path = report_dict.get("right_path", "")

        if left_path:
            self._load_image(left_path, self._left_scene, self._left_path_label)
            self._left_path = left_path
        if right_path:
            self._load_image(right_path, self._right_scene, self._right_path_label)
            self._right_path = right_path

        lw = report_dict.get("left_width", "?")
        lh = report_dict.get("left_height", "?")
        rw = report_dict.get("right_width", "?")
        rh = report_dict.get("right_height", "?")

        self._lbl_left_dims.setText(f"Left: {lw} x {lh}")
        self._lbl_right_dims.setText(f"Right: {rw} x {rh}")
        self._lbl_total_pixels.setText(
            f"Total pixels: {report_dict.get('total_pixels', '-')}"
        )
        self._lbl_diff_pixels.setText(
            f"Different pixels: {report_dict.get('different_pixels', '-')}"
        )
        diff_pct = report_dict.get("difference_pct")
        self._lbl_diff_pct.setText(
            f"Difference: {diff_pct:.2f}%" if diff_pct is not None else "Difference: -"
        )
        mean_diff = report_dict.get("mean_diff")
        self._lbl_mean_diff.setText(
            f"Mean diff: {mean_diff:.2f}" if mean_diff is not None else "Mean diff: -"
        )
        similarity_pct = report_dict.get("similarity_pct")
        if similarity_pct is not None:
            self._set_similarity(similarity_pct)
        else:
            self._lbl_similarity.setText("Similarity: -")

    # ------------------------------------------------------------------
    # Image loading
    # ------------------------------------------------------------------

    def _load_image(
        self,
        path: str,
        scene: QGraphicsScene,
        label: QLabel,
    ) -> bool:
        """Load an image into *scene* and update *label*.

        Returns True on success, False otherwise.
        """
        scene.clear()
        if not path or not os.path.isfile(path):
            label.setText("(no image loaded)")
            label.setToolTip("")
            return False

        pixmap = QPixmap(path)
        if pixmap.isNull():
            label.setText("(unreadable image)")
            label.setToolTip(path)
            return False

        scene.addItem(QGraphicsPixmapItem(pixmap))
        scene.setSceneRect(pixmap.rect().toRectF())
        label.setText(os.path.basename(path))
        label.setToolTip(path)
        return True

    # ------------------------------------------------------------------
    # Statistics computation (uses Pillow)
    # ------------------------------------------------------------------

    def _compute_stats(self, left_path: str, right_path: str) -> None:
        """Compute pixel-level statistics between two images via Pillow."""
        try:
            from PIL import Image  # type: ignore[import-untyped]
            import numpy as np  # type: ignore[import-untyped]
        except ImportError:
            self._show_error(
                "Pillow and/or NumPy not installed. "
                "Install them for pixel statistics: pip install Pillow numpy"
            )
            self._clear_stats()
            return

        try:
            left_img = Image.open(left_path).convert("RGB")
            right_img = Image.open(right_path).convert("RGB")
        except Exception as exc:
            self._show_error(f"Failed to open images for stats: {exc}")
            self._clear_stats()
            return

        lw, lh = left_img.size
        rw, rh = right_img.size

        self._lbl_left_dims.setText(f"Left: {lw} x {lh}")
        self._lbl_right_dims.setText(f"Right: {rw} x {rh}")

        # To compare, both images must share the same dimensions.
        # Crop to the overlapping region if sizes differ.
        cw = min(lw, rw)
        ch = min(lh, rh)

        left_arr = np.asarray(left_img.crop((0, 0, cw, ch)), dtype=np.int16)
        right_arr = np.asarray(right_img.crop((0, 0, cw, ch)), dtype=np.int16)

        diff = np.abs(left_arr - right_arr)

        # A pixel is "different" if any channel differs.
        pixel_diffs = np.any(diff > 0, axis=2)
        total_pixels = int(cw * ch)
        different_pixels = int(np.sum(pixel_diffs))
        diff_pct = (different_pixels / total_pixels * 100.0) if total_pixels > 0 else 0.0
        mean_diff = float(np.mean(diff))
        similarity_pct = 100.0 - diff_pct

        self._lbl_total_pixels.setText(f"Total pixels: {total_pixels:,}")
        self._lbl_diff_pixels.setText(f"Different pixels: {different_pixels:,}")
        self._lbl_diff_pct.setText(f"Difference: {diff_pct:.2f}%")
        self._lbl_mean_diff.setText(f"Mean diff: {mean_diff:.2f}")
        self._set_similarity(similarity_pct)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_similarity(self, similarity_pct: float) -> None:
        """Update the similarity label with colour-coded text."""
        colour = _similarity_color(similarity_pct)
        self._lbl_similarity.setText(f"Similarity: {similarity_pct:.2f}%")
        self._lbl_similarity.setStyleSheet(f"color: {colour.name()}; font-weight: bold;")

    def _clear_stats(self) -> None:
        """Reset all statistics labels to their default state."""
        self._lbl_left_dims.setText("Left: -")
        self._lbl_right_dims.setText("Right: -")
        self._lbl_total_pixels.setText("Total pixels: -")
        self._lbl_diff_pixels.setText("Different pixels: -")
        self._lbl_diff_pct.setText("Difference: -")
        self._lbl_mean_diff.setText("Mean diff: -")
        self._lbl_similarity.setText("Similarity: -")
        self._lbl_similarity.setStyleSheet("")

    def _show_error(self, message: str) -> None:
        """Display an error message above the image panels."""
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    _IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp);;All Files (*)"

    def _browse_left(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Left Image", "", self._IMAGE_FILTER
        )
        if path:
            if self._right_path:
                self.compare_images(path, self._right_path)
            else:
                self._load_image(path, self._left_scene, self._left_path_label)
                self._left_path = path

    def _browse_right(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Right Image", "", self._IMAGE_FILTER
        )
        if path:
            if self._left_path:
                self.compare_images(self._left_path, path)
            else:
                self._load_image(path, self._right_scene, self._right_path_label)
                self._right_path = path
