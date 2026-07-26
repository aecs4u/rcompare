"""WI-5.3 / WI-5.4 / WI-5.5 / WI-5.6 — the smaller correctness items.

* WI-5.3: CSV rows were aligned positionally, so a left-only and a right-only
  row were paired and reported as "different" while the summary claimed zero
  left-only and zero right-only. Wrong output, not just a limitation.
* WI-5.4: ``FunctionWorker`` had no cancellation path, so a long parse could
  only be orphaned — and would still deliver its result.
* WI-5.5: ``rcompare_core`` implements EXIF comparison and the CLI exposes
  ``--image-exif``, but the image view never requested or displayed it.
* WI-5.6: ``dropEvent`` kept the first two dropped paths and discarded the
  rest silently.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QMimeData, QPoint, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtCore import Qt

from teczka.main_window import MainWindow
from teczka.utils.config import AppConfig
from teczka.views.image_view import ImageView, _exif_differences
from teczka.views.table_view import TableView, _align_rows_by_key
from teczka.workers.function_worker import CancelledError, CancelToken, FunctionWorker


@pytest.fixture
def window(qapp, tmp_path):
    config = AppConfig()
    config._config_file = str(tmp_path / "pyside.json")
    win = MainWindow(config)
    yield win
    win.close()
    win.deleteLater()


def _pump(qapp, worker, timeout=3.0):
    deadline = time.monotonic() + timeout
    while worker.isRunning() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


# ---------------------------------------------------------------------------
# WI-5.4 — cooperative cancellation
# ---------------------------------------------------------------------------


def test_cancel_token_raises_on_check():
    token = CancelToken()
    token.check()  # no-op while clear
    token.cancel()
    assert token.is_set()
    with pytest.raises(CancelledError):
        token.check()


def test_a_cooperative_worker_stops_between_units(qapp):
    progressed: list[int] = []

    def work(cancel_token=None):
        for i in range(1000):
            cancel_token.check()
            progressed.append(i)
            time.sleep(0.001)
        return "finished"

    results: list[object] = []
    cancels: list[bool] = []
    worker = FunctionWorker(work, cancellable=True)
    worker.finished_with_result.connect(results.append)
    worker.cancelled.connect(lambda: cancels.append(True))
    worker.start()

    time.sleep(0.05)
    worker.cancel()
    _pump(qapp, worker)

    assert cancels == [True]
    assert results == []
    assert 0 < len(progressed) < 1000


def test_an_uncooperative_worker_still_has_its_result_suppressed(qapp):
    """Cancelling must never let a discarded operation update the GUI."""
    worker = FunctionWorker(lambda: (time.sleep(0.05), "value")[1])
    results: list[object] = []
    cancels: list[bool] = []
    worker.finished_with_result.connect(results.append)
    worker.cancelled.connect(lambda: cancels.append(True))
    worker.start()
    worker.cancel()
    _pump(qapp, worker)

    assert results == []
    assert cancels == [True]


def test_an_uncancelled_worker_delivers_its_result(qapp):
    worker = FunctionWorker(lambda: 21 * 2)
    results: list[object] = []
    worker.finished_with_result.connect(results.append)
    worker.start()
    _pump(qapp, worker)
    assert results == [42]


def test_a_failing_worker_reports_the_error(qapp):
    def boom():
        raise ValueError("nope")

    worker = FunctionWorker(boom)
    errors: list[str] = []
    worker.error.connect(errors.append)
    worker.start()
    _pump(qapp, worker)
    assert errors and "nope" in errors[0]


# ---------------------------------------------------------------------------
# WI-5.3 — key-based CSV row alignment
# ---------------------------------------------------------------------------


def test_positional_alignment_is_what_produces_wrong_output(qapp, tmp_path):
    """The documented failure: one inserted row cascades through the file."""
    left = tmp_path / "l.csv"
    right = tmp_path / "r.csv"
    left.write_text("id,name\n1,a\n2,b\n3,c\n")
    right.write_text("id,name\n1,a\n3,c\n")

    view = TableView()
    view.compare_csv(str(left), str(right))
    _pump(qapp, view._table_worker)

    # Row 2 (2,b) is paired with row 3 (3,c) and called "different"; the real
    # left-only row is invisible in that count.
    assert "1 different" in view._summary_label.text()
    view.deleteLater()


def test_key_alignment_reports_the_row_as_left_only(qapp, tmp_path):
    left = tmp_path / "l.csv"
    right = tmp_path / "r.csv"
    left.write_text("id,name\n1,a\n2,b\n3,c\n")
    right.write_text("id,name\n1,a\n3,c\n")

    view = TableView()
    view.compare_csv(str(left), str(right))
    _pump(qapp, view._table_worker)
    view._key_combo.setCurrentIndex(view._key_combo.findText("id"))
    qapp.processEvents()

    summary = view._summary_label.text()
    assert "0 different" in summary
    assert "1 left-only" in summary
    view.deleteLater()


def test_header_toggle_replaces_the_hardcoded_column_labels(qapp, tmp_path):
    """`Col 1/2/3` left no column name to select as a key."""
    left = tmp_path / "l.csv"
    right = tmp_path / "r.csv"
    left.write_text("sku,qty\nA,1\n")
    right.write_text("sku,qty\nA,2\n")

    view = TableView()
    view.compare_csv(str(left), str(right))
    _pump(qapp, view._table_worker)

    choices = [view._key_combo.itemText(i) for i in range(view._key_combo.count())]
    assert "sku" in choices and "qty" in choices

    view._header_check.setChecked(False)
    qapp.processEvents()
    choices = [view._key_combo.itemText(i) for i in range(view._key_combo.count())]
    assert "Col 1" in choices
    view.deleteLater()


def test_aligner_pairs_by_value_not_position():
    left = [["1", "a"], ["2", "b"], ["3", "c"]]
    right = [["3", "c"], ["1", "a"]]
    aligned_left, aligned_right = _align_rows_by_key(left, right, 0)

    pairs = list(zip(aligned_left, aligned_right))
    assert (["1", "a"], ["1", "a"]) in pairs
    assert (["3", "c"], ["3", "c"]) in pairs
    assert (["2", "b"], None) in pairs


def test_aligner_reports_right_only_rows():
    aligned_left, aligned_right = _align_rows_by_key([["1"]], [["1"], ["9"]], 0)
    assert (None, ["9"]) in list(zip(aligned_left, aligned_right))


def test_aligner_matches_duplicate_keys_in_order():
    left = [["k", "1"], ["k", "2"]]
    right = [["k", "1"], ["k", "2"]]
    aligned_left, aligned_right = _align_rows_by_key(left, right, 0)
    assert aligned_left == left
    assert aligned_right == right


# ---------------------------------------------------------------------------
# WI-5.5 — EXIF differences
# ---------------------------------------------------------------------------


def test_exif_differences_reports_only_differing_tags():
    left = {"Make": "Canon", "Model": "R6", "ISOSpeedRatings": "100"}
    right = {"Make": "Canon", "Model": "R5", "ISOSpeedRatings": "100"}
    assert _exif_differences(left, right) == [("Model", "R6", "R5")]


def test_exif_differences_marks_a_missing_side():
    """A stripped-metadata copy must not read as identical."""
    rows = _exif_differences({"Artist": "Ada"}, {})
    assert rows == [("Artist", "Ada", "—")]


def test_exif_differences_orders_priority_tags_first():
    left = {"ZTag": "1", "Model": "a", "Make": "x"}
    right = {"ZTag": "2", "Model": "b", "Make": "y"}
    assert [tag for tag, _, _ in _exif_differences(left, right)] == [
        "Make",
        "Model",
        "ZTag",
    ]


def test_image_view_has_an_exif_section(qapp):
    view = ImageView()
    assert view._exif_box is not None
    assert view.exif_difference_count == 0
    view.deleteLater()


def test_image_view_renders_cli_exif_differences(qapp):
    """The CLI's --image-exif payload must reach the screen."""
    view = ImageView()
    view.load_from_cli_report(
        {
            "left_exif": {"make": "Canon"},
            "right_exif": {"make": "Nikon"},
            "exif_differences": [
                {"tag_name": "Make", "left_value": "Canon", "right_value": "Nikon"},
                {"tag_name": "Artist", "left_value": "Ada", "right_value": None},
            ],
        }
    )
    assert view.exif_difference_count == 2
    assert view._exif_table.item(1, 2).text() == "—"
    view.deleteLater()


def test_image_view_explains_when_exif_was_not_requested(qapp):
    view = ImageView()
    view.load_from_cli_report({})
    assert "Settings" in view._exif_status.text()
    view.deleteLater()


# ---------------------------------------------------------------------------
# WI-5.6 — drag and drop
# ---------------------------------------------------------------------------


@pytest.fixture
def dropper(window, monkeypatch):
    """A window whose drop handler records instead of launching a scan.

    A real _on_compare() with no CLI opens a modal dialog, which would block
    the test run.
    """
    started: list[bool] = []
    monkeypatch.setattr(window, "_on_compare", lambda: started.append(True))
    window.compare_calls = started
    return window


def _drop(window, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    event = QDropEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)


def test_dropping_more_than_two_paths_says_what_was_ignored(dropper, tmp_path):
    """The extras used to be discarded in silence."""
    paths = []
    for name in ("one", "two", "three", "four"):
        directory = tmp_path / name
        directory.mkdir()
        paths.append(directory)

    _drop(dropper, paths)

    message = dropper._integrated_status.message
    assert "first two" in message
    assert "2 ignored" in message
    assert "three" in message and "four" in message
    assert dropper._left_path == str(paths[0])
    assert dropper._right_path == str(paths[1])


def test_dropping_exactly_two_paths_does_not_mention_ignoring(dropper, tmp_path):
    left, right = tmp_path / "l", tmp_path / "r"
    left.mkdir()
    right.mkdir()
    _drop(dropper, [left, right])
    assert "ignored" not in dropper._integrated_status.message


def test_dropping_one_path_fills_the_empty_side(dropper, tmp_path):
    only = tmp_path / "only"
    only.mkdir()
    _drop(dropper, [only])
    assert dropper._left_path == str(only)
    assert "drop another" in dropper._integrated_status.message
