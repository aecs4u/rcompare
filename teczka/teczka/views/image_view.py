"""Image comparison view with pixel-level statistics."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QImageReader,
    QPainter,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..workers.function_worker import FunctionWorker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GREEN = QColor("#2e7d32")
_YELLOW = QColor("#f9a825")
_RED = QColor("#c62828")

# Cap on the longest edge we'll decode at for on-screen display. Comparison
# images (camera photos, scans) can be tens of megapixels; decoding those at
# native resolution just to display/zoom them in a viewport wastes memory
# and time for no visible benefit. Pixel-statistics computation still reads
# the original file at full resolution via Pillow, unaffected by this cap.
_MAX_PREVIEW_DIM = 4096


def _load_image_for_display(path: str) -> QImage:
    """Decode *path* into a QImage, downscaling during decode (not after)
    if it exceeds :data:`_MAX_PREVIEW_DIM` on its longest edge.

    QImage is safe to create on a worker thread; QPixmap creation remains on
    the GUI thread.
    """
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > _MAX_PREVIEW_DIM:
        scale = _MAX_PREVIEW_DIM / max(size.width(), size.height())
        reader.setScaledSize(
            QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale)))
        )
    return reader.read()


@dataclass
class _PreparedImages:
    left: QImage
    right: QImage
    stats: dict[str, float | int]
    error: str = ""


def _prepare_image_pair(left_path: str, right_path: str, tolerance: int = 1) -> _PreparedImages:
    """Decode previews and calculate full-resolution stats off the GUI thread."""
    left = _load_image_for_display(left_path)
    right = _load_image_for_display(right_path)
    if left.isNull() or right.isNull():
        failed = []
        if left.isNull():
            failed.append(f"Cannot read left image: {left_path}")
        if right.isNull():
            failed.append(f"Cannot read right image: {right_path}")
        return _PreparedImages(left, right, {}, "; ".join(failed))

    try:
        from PIL import Image, ImageChops  # type: ignore[import-untyped]
    except ImportError:
        return _PreparedImages(
            left,
            right,
            {},
            "Pillow is not installed; pixel statistics are unavailable.",
        )

    try:
        with Image.open(left_path) as source:
            left_img = source.convert("RGB")
        with Image.open(right_path) as source:
            right_img = source.convert("RGB")
        lw, lh = left_img.size
        rw, rh = right_img.size
        width, height = min(lw, rw), min(lh, rh)
        difference = ImageChops.difference(
            left_img.crop((0, 0, width, height)),
            right_img.crop((0, 0, width, height)),
        )
        total = int(width * height)
        tolerance = min(255, max(0, int(tolerance)))
        threshold = [0] * (tolerance + 1) + [255] * (255 - tolerance)
        masks = [channel.point(threshold) for channel in difference.split()]
        different_mask = ImageChops.lighter(
            ImageChops.lighter(masks[0], masks[1]), masks[2]
        )
        different = total - different_mask.histogram()[0]
        histogram = difference.histogram()
        channel_delta = sum(
            (index % 256) * count for index, count in enumerate(histogram)
        )
        difference_pct = (different / total * 100.0) if total else 0.0
        return _PreparedImages(
            left,
            right,
            {
                "left_width": lw,
                "left_height": lh,
                "right_width": rw,
                "right_height": rh,
                "total_pixels": total,
                "different_pixels": different,
                "difference_pct": difference_pct,
                "mean_diff": channel_delta / (total * 3) if total else 0.0,
                "similarity_pct": 100.0 - difference_pct,
            },
        )
    except Exception as exc:  # noqa: BLE001 - shown as a non-fatal UI error
        return _PreparedImages(left, right, {}, f"Failed to compare images: {exc}")


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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def fit_to_view(self) -> None:
        """Scale the scene so the full image fits within the viewport."""
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)


class SwipePixmapItem(QGraphicsPixmapItem):
    """Pixmap item that clips its drawing to a left-to-right swipe boundary."""

    def __init__(self) -> None:
        super().__init__()
        self.clip_width = 0.0

    def set_clip_width(self, width: float) -> None:
        self.clip_width = min(max(0.0, width), float(self.pixmap().width()))
        self.update()

    def paint(self, painter, option, widget=None) -> None:
        painter.save()
        painter.setClipRect(
            QRectF(0, 0, self.clip_width, self.pixmap().height()),
            Qt.ClipOperation.IntersectClip,
        )
        super().paint(painter, option, widget)
        painter.restore()


# ---------------------------------------------------------------------------
# ImageView
# ---------------------------------------------------------------------------


class ImageView(QWidget):
    """Side-by-side image comparison widget with pixel statistics.

    Two :class:`QGraphicsView` panels display images loaded from file paths.
    A statistics panel at the bottom shows pixel-level comparison metrics
    computed via Pillow when available.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
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

        # Comparison mode controls and composited image page -----------------
        self._mode_selector = QComboBox(self)
        for label, mode in (
            ("Side by side", "side_by_side"),
            ("Overlay / blend", "overlay"),
            ("Swipe", "swipe"),
            ("Difference", "difference"),
            ("Blink", "blink"),
        ):
            self._mode_selector.addItem(label, mode)

        self._strength_label = QLabel("Blend / swipe:")
        self._strength_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._strength_slider.setRange(0, 100)
        self._strength_slider.setValue(50)
        self._strength_slider.setToolTip(
            "Set the right-image opacity in Overlay mode or the reveal boundary in Swipe mode."
        )
        self._tolerance_label = QLabel("Pixel tolerance:")
        self._tolerance_spin = QSpinBox(self)
        self._tolerance_spin.setRange(0, 255)
        self._tolerance_spin.setValue(1)
        self._tolerance_spin.setToolTip(
            "A pixel is counted as different when any RGB channel exceeds this difference."
        )
        composite_fit = QPushButton("Fit", self)
        composite_fit.setToolTip("Fit the active image comparison to view")
        composite_fit.clicked.connect(self._fit_active_view)

        mode_controls = QHBoxLayout()
        mode_controls.addWidget(QLabel("Mode:"))
        mode_controls.addWidget(self._mode_selector)
        mode_controls.addWidget(self._strength_label)
        mode_controls.addWidget(self._strength_slider, stretch=1)
        mode_controls.addWidget(self._tolerance_label)
        mode_controls.addWidget(self._tolerance_spin)
        mode_controls.addWidget(composite_fit)

        self._image_stack = QStackedWidget(self)
        self._image_stack.addWidget(splitter)
        self._composite_scene = QGraphicsScene(self)
        self._composite_view = ZoomableGraphicsView(self)
        self._composite_view.setScene(self._composite_scene)
        self._left_composite_item = QGraphicsPixmapItem()
        self._composite_scene.addItem(self._left_composite_item)
        self._right_composite_item = SwipePixmapItem()
        self._right_composite_item.setZValue(1)
        self._composite_scene.addItem(self._right_composite_item)
        self._difference_composite_item = QGraphicsPixmapItem()
        self._difference_composite_item.setZValue(2)
        self._composite_scene.addItem(self._difference_composite_item)
        self._image_stack.addWidget(self._composite_view)
        self._mode_selector.currentIndexChanged.connect(self._on_mode_changed)
        self._strength_slider.valueChanged.connect(self._render_comparison_mode)
        self._tolerance_spin.valueChanged.connect(self._on_tolerance_changed)
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)

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
        main_layout.addLayout(mode_controls)
        main_layout.addWidget(self._error_label)
        main_layout.addWidget(self._image_stack, stretch=1)
        main_layout.addWidget(self._stats_box)

        # Internal state -----------------------------------------------
        self._left_path: str = ""
        self._right_path: str = ""
        self._image_worker: FunctionWorker | None = None
        self._load_generation = 0
        self._left_preview = QImage()
        self._right_preview = QImage()
        self._blink_show_left = True
        self._strength_label.setVisible(False)
        self._strength_slider.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compare_images(self, left_path: str, right_path: str) -> None:
        """Load two images, display them, and compute pixel statistics."""
        self._error_label.setVisible(False)
        self._left_path = left_path
        self._right_path = right_path
        self._left_scene.clear()
        self._right_scene.clear()
        self._left_preview = QImage()
        self._right_preview = QImage()
        self._refresh_composite_images()

        if not os.path.isfile(left_path) or not os.path.isfile(right_path):
            self._show_error("One or both image paths do not exist.")
            self._clear_stats()
            return

        self._left_path_label.setText("Loading...")
        self._right_path_label.setText("Loading...")
        self._load_generation += 1
        generation = self._load_generation
        worker = FunctionWorker(
            _prepare_image_pair,
            left_path,
            right_path,
            self._tolerance_spin.value(),
            parent=self,
        )
        self._image_worker = worker
        worker.finished_with_result.connect(
            lambda result: self._on_images_prepared(result, generation)
        )
        worker.error.connect(self._show_error)
        worker.start()

    def _on_images_prepared(self, result: _PreparedImages, generation: int) -> None:
        if generation != self._load_generation:
            return
        left_ok = self._display_image(
            result.left, self._left_path, self._left_scene, self._left_path_label
        )
        right_ok = self._display_image(
            result.right, self._right_path, self._right_scene, self._right_path_label
        )
        if not left_ok or not right_ok:
            self._show_error(result.error or "Failed to decode one or both images.")
            self._clear_stats()
        elif result.stats:
            self._apply_stats(result.stats)
            if result.error:
                self._show_error(result.error)
        elif result.error:
            self._show_error(result.error)
            self._clear_stats()
        self._image_worker = None

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
            if scene is self._left_scene:
                self._left_preview = QImage()
            elif scene is self._right_scene:
                self._right_preview = QImage()
            label.setText("(no image loaded)")
            label.setToolTip("")
            self._refresh_composite_images()
            return False

        image = _load_image_for_display(path)
        return self._display_image(image, path, scene, label)

    def _display_image(
        self,
        image: QImage,
        path: str,
        scene: QGraphicsScene,
        label: QLabel,
    ) -> bool:
        """Create the GUI-owned pixmap and place it in a scene."""
        if image.isNull():
            label.setText("(unreadable image)")
            label.setToolTip(path)
            return False

        if scene is self._left_scene:
            self._left_preview = image
        elif scene is self._right_scene:
            self._right_preview = image
        pixmap = QPixmap.fromImage(image)
        scene.addItem(QGraphicsPixmapItem(pixmap))
        scene.setSceneRect(pixmap.rect().toRectF())
        label.setText(os.path.basename(path))
        label.setToolTip(path)
        if not self._left_preview.isNull() and not self._right_preview.isNull():
            self._refresh_composite_images()
        return True

    def _on_mode_changed(self, _index: int) -> None:
        self._render_comparison_mode()

    def _on_tolerance_changed(self, _value: int) -> None:
        if self._left_path and self._right_path:
            self.compare_images(self._left_path, self._right_path)

    def _fit_active_view(self) -> None:
        if self._image_stack.currentIndex() == 0:
            self._left_view.fit_to_view()
            self._right_view.fit_to_view()
        else:
            self._composite_view.fit_to_view()

    def _refresh_composite_images(self) -> None:
        """Refresh the layered scene after a new pair has finished loading."""
        if self._left_preview.isNull() or self._right_preview.isNull():
            self._left_composite_item.setPixmap(QPixmap())
            self._right_composite_item.setPixmap(QPixmap())
            self._difference_composite_item.setPixmap(QPixmap())
            self._composite_scene.setSceneRect(QRectF())
            self._render_comparison_mode()
            return

        left_pixmap = QPixmap.fromImage(self._left_preview)
        right_pixmap = QPixmap.fromImage(self._right_preview)
        self._left_composite_item.setPixmap(left_pixmap)
        self._right_composite_item.setPixmap(right_pixmap)
        width = max(left_pixmap.width(), right_pixmap.width())
        height = max(left_pixmap.height(), right_pixmap.height())
        self._right_composite_item.set_clip_width(width)
        self._difference_composite_item.setPixmap(
            QPixmap.fromImage(self._make_difference_image(self._left_preview, self._right_preview))
        )
        self._composite_scene.setSceneRect(QRectF(0, 0, width, height))
        self._render_comparison_mode()

    @staticmethod
    def _make_difference_image(left: QImage, right: QImage) -> QImage:
        """Create a Difference-mode image, aligning both inputs at the origin."""
        width = max(left.width(), right.width())
        height = max(left.height(), right.height())
        result = QImage(width, height, QImage.Format.Format_RGB32)
        result.fill(Qt.GlobalColor.black)
        painter = QPainter(result)
        painter.drawImage(0, 0, left)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
        painter.drawImage(0, 0, right)
        painter.end()
        return result

    def _render_comparison_mode(self, _value: int = 0) -> None:
        """Select the active presentation and apply opacity/swipe controls."""
        mode = self._mode_selector.currentData()
        side_by_side = mode == "side_by_side"
        self._image_stack.setCurrentIndex(0 if side_by_side else 1)
        uses_strength = mode in ("overlay", "swipe")
        self._strength_label.setVisible(uses_strength)
        self._strength_slider.setVisible(uses_strength)

        has_images = not self._left_preview.isNull() and not self._right_preview.isNull()
        if mode == "blink" and has_images:
            if not self._blink_timer.isActive():
                self._blink_show_left = True
                self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._blink_show_left = True

        if not has_images:
            return

        strength = self._strength_slider.value() / 100.0
        self._left_composite_item.setOpacity(1.0)
        self._right_composite_item.setOpacity(1.0)
        self._left_composite_item.setVisible(False)
        self._right_composite_item.setVisible(False)
        self._difference_composite_item.setVisible(False)

        if mode == "overlay":
            self._left_composite_item.setVisible(True)
            self._right_composite_item.setVisible(True)
            self._right_composite_item.set_clip_width(self._composite_scene.sceneRect().width())
            self._right_composite_item.setOpacity(strength)
        elif mode == "swipe":
            self._left_composite_item.setVisible(True)
            scene_rect = self._composite_scene.sceneRect()
            self._right_composite_item.setVisible(True)
            self._right_composite_item.set_clip_width(scene_rect.width() * strength)
        elif mode == "difference":
            self._difference_composite_item.setVisible(True)
        elif mode == "blink":
            self._left_composite_item.setVisible(self._blink_show_left)
            self._right_composite_item.setVisible(not self._blink_show_left)
            scene_rect = self._composite_scene.sceneRect()
            self._right_composite_item.set_clip_width(scene_rect.width())

    def _toggle_blink(self) -> None:
        if self._mode_selector.currentData() != "blink":
            self._blink_timer.stop()
            return
        self._blink_show_left = not self._blink_show_left
        self._render_comparison_mode()

    # ------------------------------------------------------------------
    # Statistics computation (uses Pillow)
    # ------------------------------------------------------------------

    def _compute_stats(self, left_path: str, right_path: str) -> None:
        """Compute pixel-level statistics between two images via Pillow."""
        try:
            import numpy as np  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]
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
        except (OSError, ValueError) as exc:
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

    def _apply_stats(self, stats: dict[str, float | int]) -> None:
        """Render statistics calculated by the background worker."""
        self._lbl_left_dims.setText(
            f"Left: {int(stats['left_width'])} x {int(stats['left_height'])}"
        )
        self._lbl_right_dims.setText(
            f"Right: {int(stats['right_width'])} x {int(stats['right_height'])}"
        )
        self._lbl_total_pixels.setText(
            f"Total pixels: {int(stats['total_pixels']):,}"
        )
        self._lbl_diff_pixels.setText(
            f"Different pixels: {int(stats['different_pixels']):,}"
        )
        self._lbl_diff_pct.setText(f"Difference: {stats['difference_pct']:.2f}%")
        self._lbl_mean_diff.setText(f"Mean diff: {stats['mean_diff']:.2f}")
        self._set_similarity(float(stats["similarity_pct"]))

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
