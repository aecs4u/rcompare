"""Tests for teczka widgets."""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QFrame, QToolButton

from teczka.views.image_view import ImageView
from teczka.views.folder_view import FolderView
from teczka.models.tree_model import COL_RIGHT_SIZE, COL_STATUS
from teczka.dialogs.splash_dialog import SplashDialog
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


def test_splash_has_professional_welcome_content(qtbot):
    dialog = SplashDialog()
    qtbot.addWidget(dialog)

    assert dialog.objectName() == "splashDialog"
    assert dialog.minimumWidth() >= 700
    cards = [
        frame
        for frame in dialog.findChildren(QFrame)
        if frame.objectName() == "featureCard"
    ]
    assert len(cards) == 3
    assert dialog._btn_start.isDefault()
    assert dialog.should_show_again()

    dialog._chk_hide.setChecked(True)
    assert not dialog.should_show_again()


def test_folder_panes_offer_persistent_selectable_columns(qtbot):
    view = FolderView()
    qtbot.addWidget(view)

    column_buttons = [
        button
        for button in view.findChildren(QToolButton)
        if button.objectName() == "columnsButton"
    ]
    assert len(column_buttons) == 2
    assert view.left_tree.isColumnHidden(COL_STATUS)
    assert (
        view.right_tree.header().visualIndex(COL_RIGHT_SIZE)
        < view.right_tree.header().visualIndex(COL_STATUS)
    )

    status_action = next(
        action
        for action in view._column_menus[view.left_tree].actions()
        if action.data() == COL_STATUS
    )
    status_action.setChecked(True)
    view.left_tree.setColumnWidth(COL_STATUS, 137)
    assert not view.left_tree.isColumnHidden(COL_STATUS)

    saved = view.column_widths()
    restored = FolderView()
    qtbot.addWidget(restored)
    restored.set_column_widths(saved)

    assert not restored.left_tree.isColumnHidden(COL_STATUS)
    assert restored.left_tree.columnWidth(COL_STATUS) == 137
    assert restored.right_tree.isColumnHidden(COL_STATUS)
