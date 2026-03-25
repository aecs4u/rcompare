"""Tests for teczka widgets."""

from __future__ import annotations

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
