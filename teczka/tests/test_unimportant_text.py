"""Tests for unimportant-text rules in result processing and previews."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QMessageBox
from teczka.dialogs.unimportant_rules_dialog import UnimportantTextRulesDialog
from teczka.utils.cli_bridge import (
    DiffEntry,
    DiffStatus,
    FileSide,
    ScanReport,
    ScanSummary,
)
from teczka.utils.unimportant_text import (
    RuleValidationError,
    apply_to_report,
    normalize_lines,
    validate_rules,
)
from teczka.views.text_view import TextView, _compute_file_diff

RULE = {
    "pattern": r"^Build-ID=.*$",
    "replacement": "Build-ID=<ignored>",
    "description": "Generated build identifier",
}


def test_rules_normalize_text_in_order_and_validate_patterns():
    rules = validate_rules([RULE])
    assert normalize_lines("Build-ID=abc\nvalue=1\n", rules) == [
        "Build-ID=<ignored>",
        "value=1",
    ]

    try:
        validate_rules([{"pattern": "(", "replacement": "", "description": ""}])
    except RuleValidationError as exc:
        assert "invalid pattern" in str(exc)
    else:
        raise AssertionError("invalid regular expression was accepted")

    try:
        validate_rules([{"pattern": r"(\w+)", "replacement": r"\2", "description": ""}])
    except RuleValidationError as exc:
        assert "invalid replacement" in str(exc)
    else:
        raise AssertionError("invalid replacement reference was accepted")


def test_folder_report_reclassifies_normalized_text_and_recomputes_summary(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "generated.txt").write_text("Build-ID=abc\nvalue=1\n")
    (right / "generated.txt").write_text("Build-ID=xyz\nvalue=1\n")
    (left / "real.txt").write_text("value=left\n")
    (right / "real.txt").write_text("value=right\n")

    file_side = FileSide(size=20, modified_unix=1, is_dir=False)
    report = ScanReport(
        left=str(left),
        right=str(right),
        summary=ScanSummary(total=2, same=0, different=2, orphan_left=0, orphan_right=0, unchecked=0),
        entries=[
            DiffEntry("generated.txt", DiffStatus.DIFFERENT, file_side, file_side),
            DiffEntry("real.txt", DiffStatus.DIFFERENT, file_side, file_side),
        ],
    )

    updated = apply_to_report(report, str(left), str(right), [RULE])

    assert updated == 1
    assert [entry.status for entry in report.entries] == [
        DiffStatus.SAME,
        DiffStatus.DIFFERENT,
    ]
    assert report.summary.total == 2
    assert report.summary.same == 1
    assert report.summary.different == 1


def test_text_preview_shows_ignored_values_without_marking_them_different(tmp_path):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("Build-ID=abc\nvalue=1\n")
    right.write_text("Build-ID=xyz\nvalue=1\n")

    result = _compute_file_diff(str(left), str(right), QColor("white"), [RULE])

    assert result.display_left == ["Build-ID=abc", "value=1"]
    assert result.display_right == ["Build-ID=xyz", "value=1"]
    assert result.colors_left == [QColor("white"), QColor("white")]
    assert result.colors_right == [QColor("white"), QColor("white")]


def test_unreadable_text_encoding_keeps_original_scan_status(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "bad.txt").write_bytes(b"\xffleft")
    (right / "bad.txt").write_bytes(b"\xffright")
    file_side = FileSide(size=5, modified_unix=1, is_dir=False)
    report = ScanReport(
        left=str(left),
        right=str(right),
        summary=ScanSummary(total=1, same=0, different=1, orphan_left=0, orphan_right=0, unchecked=0),
        entries=[DiffEntry("bad.txt", DiffStatus.DIFFERENT, file_side, file_side)],
    )

    assert apply_to_report(report, str(left), str(right), [RULE]) == 0
    assert report.entries[0].status == DiffStatus.DIFFERENT


def test_text_view_can_match_folder_criteria_rule_policy(qapp, qtbot, tmp_path):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("Build-ID=abc\n")
    right.write_text("Build-ID=xyz\n")
    view = TextView()
    qtbot.addWidget(view)

    view.compare_files(str(left), str(right), [RULE], apply_unimportant_rules=False)
    qtbot.waitUntil(lambda: view.has_comparison_data, timeout=5000)
    base = view._left_editor.palette().color(view._left_editor.palette().ColorRole.Base)
    assert view._left_editor._line_colors[0] != base

    view.compare_files(str(left), str(right), [RULE], apply_unimportant_rules=True)
    qtbot.waitUntil(lambda: view.has_comparison_data, timeout=5000)
    assert view._left_editor._line_colors[0] == base


def test_unimportant_rules_dialog_edits_and_rejects_invalid_regex(qapp, monkeypatch):
    dialog = UnimportantTextRulesDialog([RULE])
    assert dialog.rules() == [RULE]
    dialog._table.item(0, 0).setText("(")
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda _parent, _title, message: messages.append(message)),
    )

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert messages and "invalid pattern" in messages[0]
    dialog.deleteLater()
    qapp.processEvents()


def test_unimportant_rules_dialog_accepts_valid_edits(qapp):
    dialog = UnimportantTextRulesDialog([RULE])
    dialog._table.item(0, 1).setText("Build-ID=<normalized>")

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.rules()[0]["replacement"] == "Build-ID=<normalized>"
    dialog.deleteLater()
    qapp.processEvents()
