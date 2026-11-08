"""Tests for teczka widgets."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from teczka.views.image_view import ImageView, _prepare_image_pair
from teczka.widgets.breadcrumb_bar import BreadcrumbBar
from teczka.widgets.color_legend import ColorLegend
from teczka.widgets.diff_overview_bar import DiffOverviewBar
from teczka.widgets.diff_text_edit import DiffTextEdit
from teczka.widgets.filter_bar import FilterBar
from teczka.widgets.integrated_status_bar import IntegratedStatusBar


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


class TestIntegratedStatusBar:
    def test_search_mode_and_error_state(self, qapp):
        widget = IntegratedStatusBar()
        received = []
        widget.search_mode_changed.connect(received.append)

        widget.set_search_mode("wildcard", emit=True)
        widget.set_search_error("unterminated character set")
        assert widget.search_mode == "wildcard"
        assert received == ["wildcard"]
        assert widget._search_edit.property("searchError") is True
        assert widget._search_edit.toolTip() == "unterminated character set"

        widget.set_search_error("")
        assert widget._search_edit.property("searchError") is False


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


def test_image_view_modes_and_cli_style_pixel_tolerance(qtbot, tmp_path):
    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(QColor(10, 20, 30))
    assert image.save(str(left))
    image.fill(QColor(10, 23, 30))
    assert image.save(str(right))

    stats_exact = _prepare_image_pair(str(left), str(right), tolerance=1).stats
    stats_tolerant = _prepare_image_pair(str(left), str(right), tolerance=3).stats
    assert stats_exact["different_pixels"] == 256
    assert stats_tolerant["different_pixels"] == 0

    view = ImageView()
    qtbot.addWidget(view)
    view.compare_images(str(left), str(right))
    qtbot.waitUntil(lambda: view._image_worker is None, timeout=5_000)
    view._tolerance_spin.setValue(3)
    qtbot.waitUntil(
        lambda: (
            view._image_worker is None
            and view._lbl_diff_pixels.text() == "Different pixels: 0"
        ),
        timeout=5_000,
    )

    view._mode_selector.setCurrentIndex(view._mode_selector.findData("overlay"))
    assert view._image_stack.currentIndex() == 1
    assert view._right_composite_item.opacity() == 0.5

    view._mode_selector.setCurrentIndex(view._mode_selector.findData("swipe"))
    view._strength_slider.setValue(25)
    assert view._right_composite_item.clip_width == 4
    swipe_render = QImage(16, 16, QImage.Format.Format_RGB32)
    painter = QPainter(swipe_render)
    view._composite_scene.render(painter, QRectF(0, 0, 16, 16), QRectF(0, 0, 16, 16))
    painter.end()
    assert swipe_render.pixelColor(2, 2) == QColor(10, 23, 30)
    assert swipe_render.pixelColor(10, 2) == QColor(10, 20, 30)

    view._mode_selector.setCurrentIndex(view._mode_selector.findData("difference"))
    difference = view._difference_composite_item.pixmap().toImage().pixelColor(0, 0)
    assert (difference.red(), difference.green(), difference.blue()) == (0, 3, 0)

    view._mode_selector.setCurrentIndex(view._mode_selector.findData("blink"))
    assert view._blink_timer.isActive()
    view._toggle_blink()
    assert not view._left_composite_item.isVisible()
    assert view._right_composite_item.isVisible()


def test_syntax_highlighting_keeps_diff_backgrounds_and_ignores_keywords_in_strings(
    qapp,
):
    from teczka.widgets.syntax_highlighter import language_for_path

    editor = DiffTextEdit()
    line_background = QColor("#fff9c4")
    editor.set_syntax_language(language_for_path("sample.py"))
    editor.set_content(
        ["def greet(): return 'if 42'"],
        [line_background],
        ["1"],
    )
    qapp.processEvents()

    ranges = editor.document().firstBlock().layout().formats()

    def color_at(position: int) -> QColor | None:
        for item in ranges:
            if item.start <= position < item.start + item.length:
                return item.format.foreground().color()
        return None

    assert color_at(0) == QColor("#005cc5")  # `def`
    assert color_at(4) == QColor("#6f42c1")  # function name
    assert color_at(20) == QColor("#0a7d3b")  # the whole string, including `if 42`
    assert editor._line_colors == [line_background]
    assert language_for_path("sftp://example.invalid/src/main.rs") == "rust"
    assert language_for_path("notes.unknown") is None


def test_syntax_highlighting_tracks_multiline_strings_and_comments(qapp):
    editor = DiffTextEdit()
    editor.set_syntax_language("python")
    editor.set_content(
        ["message = '''first", "if 42 is still a string", "last'''", "# comment"],
        [QColor("#ffffff")] * 4,
        ["1", "2", "3", "4"],
    )
    qapp.processEvents()

    blocks = editor.document().begin()
    blocks = [blocks, blocks.next(), blocks.next().next(), blocks.next().next().next()]

    def formatted_color(block, position: int) -> QColor | None:
        for item in block.layout().formats():
            if item.start <= position < item.start + item.length:
                return item.format.foreground().color()
        return None

    assert formatted_color(blocks[1], 0) == QColor("#0a7d3b")
    assert formatted_color(blocks[3], 0) == QColor("#6a737d")
