"""Image comparison view with pixel-level statistics."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
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


# EXIF tags worth surfacing in a comparison, in the order photographers read
# them. Anything else the files carry is appended alphabetically afterwards.
_EXIF_PRIORITY_TAGS: tuple[str, ...] = (
    "Make",
    "Model",
    "LensModel",
    "DateTimeOriginal",
    "DateTime",
    "ExposureTime",
    "FNumber",
    "ISOSpeedRatings",
    "FocalLength",
    "Orientation",
    "Software",
    "Artist",
    "Copyright",
    "ColorSpace",
    "XResolution",
    "YResolution",
)


def _read_exif(path: str) -> dict[str, str]:
    """Return a ``tag name -> printable value`` map for *path*.

    Returns an empty dict when the file carries no EXIF, when Pillow is
    unavailable, or when the payload is malformed — none of which is an error
    worth interrupting an image comparison for.
    """
    try:
        from PIL import Image  # type: ignore[import-untyped]
        from PIL.ExifTags import TAGS  # type: ignore[import-untyped]
    except ImportError:
        return {}

    try:
        with Image.open(path) as source:
            raw = source.getexif()
            if not raw:
                return {}
            result: dict[str, str] = {}
            for tag_id, value in raw.items():
                name = TAGS.get(tag_id, f"Tag{tag_id}")
                if isinstance(value, bytes):
                    text = value.decode("utf-8", errors="replace").strip("\x00").strip()
                else:
                    text = str(value).strip()
                if text:
                    result[str(name)] = text
            return result
    except Exception:  # noqa: BLE001 - absent/corrupt EXIF is not a failure
        return {}


def _exif_differences(
    left: dict[str, str], right: dict[str, str]
) -> list[tuple[str, str, str]]:
    """Return ``(tag, left value, right value)`` for every differing tag.

    Tags present on one side only are reported with an em dash for the missing
    side, so a stripped-metadata copy is visible rather than silently equal.
    """
    names = set(left) | set(right)
    ordered = [tag for tag in _EXIF_PRIORITY_TAGS if tag in names]
    ordered += sorted(names - set(_EXIF_PRIORITY_TAGS))

    rows: list[tuple[str, str, str]] = []
    for tag in ordered:
        left_value = left.get(tag, "")
        right_value = right.get(tag, "")
        if left_value == right_value:
            continue
        rows.append((tag, left_value or "—", right_value or "—"))
    return rows


@dataclass
class _PreparedImages:
    left: QImage
    right: QImage
    stats: dict[str, float | int]
    error: str = ""
    exif_differences: list[tuple[str, str, str]] = field(default_factory=list)
    exif_available: bool = False


def _prepare_image_pair(
    left_path: str, right_path: str, *, cancel_token=None
) -> _PreparedImages:
    """Decode previews and calculate full-resolution stats off the GUI thread."""
    left = _load_image_for_display(left_path)
    right = _load_image_for_display(right_path)
    if cancel_token is not None:
        cancel_token.check()
    if left.isNull() or right.isNull():
        failed = []
        if left.isNull():
            failed.append(f"Cannot read left image: {left_path}")
        if right.isNull():
            failed.append(f"Cannot read right image: {right_path}")
        return _PreparedImages(left, right, {}, "; ".join(failed))

    left_exif = _read_exif(left_path)
    right_exif = _read_exif(right_path)
    exif_available = bool(left_exif or right_exif)
    exif_rows = _exif_differences(left_exif, right_exif)
    if cancel_token is not None:
        cancel_token.check()

    try:
        from PIL import Image, ImageChops  # type: ignore[import-untyped]
    except ImportError:
        return _PreparedImages(
            left,
            right,
            {},
            "Pillow is not installed; pixel statistics are unavailable.",
            exif_rows,
            exif_available,
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
        threshold = [0] + [255] * 255
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
        if cancel_token is not None:
            cancel_token.check()
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
            "",
            exif_rows,
            exif_available,
        )
    except Exception as exc:  # noqa: BLE001 - shown as a non-fatal UI error
        return _PreparedImages(
            left,
            right,
            {},
            f"Failed to compare images: {exc}",
            exif_rows,
            exif_available,
        )


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

        # EXIF differences ---------------------------------------------
        # rcompare_core has implemented EXIF comparison all along and the CLI
        # exposes --image-exif; this view simply never showed the result.
        self._exif_box = QGroupBox("EXIF Differences")
        exif_layout = QVBoxLayout(self._exif_box)
        exif_layout.setContentsMargins(6, 6, 6, 6)

        self._exif_status = QLabel("No image loaded.")
        self._exif_status.setWordWrap(True)
        exif_layout.addWidget(self._exif_status)

        self._exif_table = QTableWidget(0, 3)
        self._exif_table.setHorizontalHeaderLabels(["Tag", "Left", "Right"])
        self._exif_table.verticalHeader().setVisible(False)
        self._exif_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._exif_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._exif_table.setAlternatingRowColors(True)
        self._exif_table.setMaximumHeight(160)
        self._exif_table.setAccessibleName("EXIF metadata differences")
        header = self._exif_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._exif_table.setVisible(False)
        exif_layout.addWidget(self._exif_table)

        # Error label (hidden by default) ------------------------------
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: palette(bright-text); font-weight: bold;")
        self._error_label.setVisible(False)

        # Main layout --------------------------------------------------
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(QLabel("<b>Image Compare</b>"))
        main_layout.addWidget(self._error_label)
        main_layout.addWidget(splitter, stretch=1)
        main_layout.addWidget(self._stats_box)
        main_layout.addWidget(self._exif_box)

        # Internal state -----------------------------------------------
        self._left_path: str = ""
        self._right_path: str = ""
        self._image_worker: FunctionWorker | None = None
        self._load_generation = 0

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

        if not os.path.isfile(left_path) or not os.path.isfile(right_path):
            self._show_error("One or both image paths do not exist.")
            self._clear_stats()
            return

        self._left_path_label.setText("Loading...")
        self._right_path_label.setText("Loading...")
        self._exif_status.setText("Reading metadata…")
        self._exif_table.setVisible(False)
        self._load_generation += 1
        generation = self._load_generation
        # Supersede any in-flight comparison rather than letting it finish and
        # race the new one to the labels.
        self.cancel_pending()
        worker = FunctionWorker(
            _prepare_image_pair,
            left_path,
            right_path,
            parent=self,
            cancellable=True,
        )
        self._image_worker = worker
        worker.finished_with_result.connect(
            lambda result: self._on_images_prepared(result, generation)
        )
        worker.error.connect(self._show_error)
        worker.cancelled.connect(self._on_load_cancelled)
        worker.start()

    def cancel_pending(self) -> None:
        """Cancel an in-flight image comparison, if any."""
        worker = self._image_worker
        if worker is not None and worker.isRunning():
            worker.cancel()

    def _on_load_cancelled(self) -> None:
        self._image_worker = None

    def _on_images_prepared(self, result: _PreparedImages, generation: int) -> None:
        if generation != self._load_generation:
            return
        self._apply_exif(result)
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

        self._apply_cli_exif(report_dict)

    def _apply_cli_exif(self, report_dict: dict[str, Any]) -> None:
        """Render EXIF differences produced by ``rcompare_cli --image-exif``.

        The CLI emits ``exif_differences`` as a list of
        ``{tag_name, left_value, right_value}`` objects (rcompare_core's
        ``ExifDifference``), plus ``left_exif``/``right_exif`` metadata blocks
        that tell us whether EXIF was read at all.
        """
        raw = report_dict.get("exif_differences")
        if raw is None:
            # --image-exif was not requested for this scan.
            self._exif_table.setRowCount(0)
            self._exif_table.setVisible(False)
            self._exif_status.setText(
                "EXIF comparison is off. Enable it in Settings > Diff Options."
            )
            return

        rows = [
            (
                str(item.get("tag_name", "")),
                str(item.get("left_value") or "—"),
                str(item.get("right_value") or "—"),
            )
            for item in raw
            if isinstance(item, dict)
        ]
        available = bool(report_dict.get("left_exif") or report_dict.get("right_exif"))
        self._apply_exif(
            _PreparedImages(
                QImage(), QImage(), {}, "", rows, available
            )
        )

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

        pixmap = QPixmap.fromImage(image)
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

    def _apply_exif(self, result: _PreparedImages) -> None:
        """Render the EXIF differences table from a prepared comparison."""
        rows = result.exif_differences
        self._exif_table.setRowCount(len(rows))
        for row, (tag, left_value, right_value) in enumerate(rows):
            for column, text in enumerate((tag, left_value, right_value)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self._exif_table.setItem(row, column, item)
        self._exif_table.setVisible(bool(rows))

        if not result.exif_available:
            self._exif_status.setText("Neither image carries EXIF metadata.")
        elif not rows:
            self._exif_status.setText("EXIF metadata is identical on both sides.")
        else:
            plural = "tag" if len(rows) == 1 else "tags"
            self._exif_status.setText(f"{len(rows)} EXIF {plural} differ.")

    def _clear_exif(self) -> None:
        self._exif_table.setRowCount(0)
        self._exif_table.setVisible(False)
        self._exif_status.setText("No image loaded.")

    @property
    def exif_difference_count(self) -> int:
        """Number of differing EXIF tags currently displayed (used by tests)."""
        return self._exif_table.rowCount()

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
        self._clear_exif()

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
