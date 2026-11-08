"""Folder and text report export coverage."""

from __future__ import annotations

import csv
import json
from xml.etree import ElementTree

from PySide6.QtWidgets import QFileDialog

from teczka.dialogs.export_dialog import ExportDialog
from teczka.main_window import MainWindow
from teczka.utils.cli_bridge import (
    DiffEntry,
    DiffStatus,
    FileSide,
    ScanReport,
    ScanSummary,
)
from teczka.utils.config import AppConfig
from teczka.utils.criteria import CompareCriteria, apply_criteria
from teczka.utils.report_export import export_folder_report, text_diff_html


def _rows():
    return [
        {
            "path": "src/<main>.py",
            "status": "different",
            "is_directory": False,
            "left_size": 12,
            "left_modified_unix": 100,
            "right_size": 15,
            "right_modified_unix": 101,
        },
        {
            "path": "same.txt",
            "status": "same",
            "is_directory": False,
            "left_size": 3,
            "left_modified_unix": 200,
            "right_size": 3,
            "right_modified_unix": 200,
        },
    ]


def test_folder_report_writes_valid_json_csv_and_xml(tmp_path):
    rows = _rows()
    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "report.csv"
    xml_path = tmp_path / "report.xml"

    export_folder_report(rows, str(json_path), "json", left_root="L&", right_root="R")
    export_folder_report(rows, str(csv_path), "csv")
    export_folder_report(rows, str(xml_path), "xml", left_root="L&", right_root="R")

    report = json.loads(json_path.read_text())
    assert report["summary"] == {
        "total": 2,
        "identical": 1,
        "different": 1,
        "left_only": 0,
        "right_only": 0,
        "unchecked": 0,
    }
    assert report["entries"][0]["path"] == "src/<main>.py"
    with csv_path.open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert [row["path"] for row in csv_rows] == ["src/<main>.py", "same.txt"]

    root = ElementTree.parse(xml_path).getroot()
    assert root.findtext("left") == "L&"
    assert root.find("entries/entry/path").text == "src/<main>.py"


def test_folder_html_escapes_paths_and_summary_uses_exported_rows(tmp_path):
    output = tmp_path / "report.html"
    export_folder_report(_rows()[:1], str(output), "html", left_root="<lhs>")
    html = output.read_text()
    assert "&lt;lhs&gt;" in html
    assert "src/&lt;main&gt;.py" in html
    assert "Identical: 0" in html
    assert "Different: 1" in html


def test_empty_csv_still_has_headers_and_honors_size_option(tmp_path):
    output = tmp_path / "empty.csv"
    ExportDialog.export_results([], str(output), "csv", include_sizes=False)
    headers = next(csv.reader(output.open(encoding="utf-8")))
    assert "path" in headers
    assert "left_size" not in headers
    assert "right_size" not in headers


def test_export_dialog_keeps_suggested_extension_in_sync(qapp):
    dialog = ExportDialog()
    assert dialog.file_path.endswith(".csv")
    dialog._radio_html.click()
    assert dialog.format == "html"
    assert dialog.file_path.endswith(".html")
    dialog._radio_xml.click()
    assert dialog.file_path.endswith(".xml")


def test_text_diff_html_escapes_content_and_labels():
    html = text_diff_html("left<&", "right", ["<removed>"], ["added & more"])
    assert "left&lt;&amp;" in html
    assert "&lt;removed&gt;" in html
    assert "added &amp; more" in html
    assert 'class="changed"' in html


def test_main_window_report_rows_follow_folder_proxy_filters(
    qapp, qtbot, tmp_path, monkeypatch
):
    window = MainWindow(AppConfig(cli_path="/missing/rcompare_cli"))
    qtbot.addWidget(window)
    window._current_report = ScanReport(
        left="left",
        right="right",
        summary=ScanSummary(total=3, same=1, different=1, orphan_left=1, orphan_right=0, unchecked=0),
        entries=[
            DiffEntry("changed.txt", DiffStatus.DIFFERENT, FileSide(1, 1, False), FileSide(2, 2, False)),
            DiffEntry("same.txt", DiffStatus.SAME, FileSide(1, 1, False), FileSide(1, 1, False)),
            DiffEntry("only-left.txt", DiffStatus.ORPHAN_LEFT, FileSide(4, 1, False), None),
        ],
    )
    window._rebuild_folder_tree_from_report()
    window._folder_view.set_filters(
        show_identical=False,
        show_different=True,
        show_left_only=False,
        show_right_only=False,
        search_text="changed",
    )

    rows = window._current_visible_folder_report_rows()
    assert [row["path"] for row in rows] == ["changed.txt"]
    assert rows[0]["status"] == "different"

    # Export consumes the criteria-adjusted report, then applies the view proxy.
    criteria_report = ScanReport(
        left="left",
        right="right",
        summary=ScanSummary(total=1, same=0, different=1, orphan_left=0, orphan_right=0, unchecked=0),
        entries=[
            DiffEntry("changed.txt", DiffStatus.DIFFERENT, FileSide(5, 1, False), FileSide(5, 9000, False)),
        ],
    )
    apply_criteria(criteria_report, CompareCriteria(mode="size"))
    window._current_report = criteria_report
    window._rebuild_folder_tree_from_report()
    window._folder_view.set_filters(True, True, True, True, False, "changed", "show_no_orphans")
    rows = window._current_visible_folder_report_rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "same"

    output = tmp_path / "visible.html"

    def accept_export(dialog):
        dialog._path_edit.setText(str(output))
        dialog._radio_html.setChecked(True)
        return 1

    monkeypatch.setattr(ExportDialog, "exec", accept_export)
    window._act_export_report.trigger()
    assert "changed.txt" in output.read_text()
    assert "Identical: 1" in output.read_text()


def test_text_html_export_menu_action_writes_active_comparison(
    qapp, qtbot, tmp_path, monkeypatch
):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("unchanged\nold <value>\n")
    right.write_text("unchanged\nnew & value\n")
    output = tmp_path / "text-diff.html"
    window = MainWindow(AppConfig(cli_path="/missing/rcompare_cli"))
    qtbot.addWidget(window)
    window._text_view.compare_files(str(left), str(right))
    qtbot.waitUntil(lambda: window._text_view.has_comparison_data, timeout=5_000)
    window._switch_view(2)
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *_args: (str(output), "HTML Files (*.html)")),
    )

    window._act_export_text_html.trigger()

    html = output.read_text(encoding="utf-8")
    assert "left.txt" in html
    assert "right.txt" in html
    assert "old &lt;value&gt;" in html
    assert "new &amp; value" in html
