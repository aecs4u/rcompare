"""Tests for teczka widgets."""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage

from teczka.views.image_view import ImageView
from teczka.widgets.diff_text_edit import DiffTextEdit
from teczka.widgets.filter_bar import FilterBar
from teczka.widgets.color_legend import ColorLegend
from teczka.widgets.diff_overview_bar import DiffOverviewBar
from teczka.widgets.breadcrumb_bar import BreadcrumbBar


class TestDiffTextEdit:
    def test_instantiation(self, qapp):
        widget = DiffTextEdit()
        assert widget is not None

    def test_set_editable(self, qapp):
        widget = DiffTextEdit()
        widget.set_editable(True)
        assert widget.isReadOnly() is False


class TestFilterBar:
    def test_instantiation(self, qapp):
        widget = FilterBar()
        assert widget is not None


class TestColorLegend:
    def test_instantiation(self, qapp):
        widget = ColorLegend()
        assert widget is not None


class TestDiffOverviewBar:
    def test_instantiation(self, qapp):
        widget = DiffOverviewBar()
        assert widget is not None


class TestBreadcrumbBar:
    def test_instantiation(self, qapp):
        widget = BreadcrumbBar()
        assert widget is not None


def test_image_view_decodes_pair_in_background(qtbot, tmp_path):
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(left))
    image.fill(QColor("blue"))
    assert image.save(str(right))

    view = ImageView()
    qtbot.addWidget(view)
    view.compare_images(str(left), str(right))
    qtbot.waitUntil(lambda: view._image_worker is None, timeout=5_000)

    assert len(view._left_scene.items()) == 1
    assert len(view._right_scene.items()) == 1
    assert view._lbl_total_pixels.text() == "Total pixels: 256"
    assert view._lbl_diff_pixels.text() == "Different pixels: 256"
