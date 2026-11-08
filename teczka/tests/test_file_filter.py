from types import SimpleNamespace as NS

from teczka.utils.cli_bridge import DiffStatus
from teczka.utils.file_filter import apply_to_report, filter_entries, parse_filter


def _e(path, is_dir=False, status=DiffStatus.DIFFERENT):
    side = NS(is_dir=is_dir)
    return NS(path=path, status=status, left=side, right=side)


ENTRIES = [
    _e("src", True), _e("src/a.py"), _e("src/b.tmp"),
    _e("build", True), _e("build/x.o"),
    _e("docs", True), _e("docs/readme.md"), _e("top.py"),
]


def paths(text):
    return [e.path for e in filter_entries(list(ENTRIES), parse_filter(text))]


def test_empty_filter_keeps_all():
    assert not parse_filter("").active
    assert len(paths("")) == len(ENTRIES)


def test_include_globs_keep_parent_folders_only():
    assert paths("*.py") == ["src", "src/a.py", "top.py"]


def test_exclude_file_and_folder():
    got = paths("-*.tmp;-build/")
    assert "src/b.tmp" not in got and "build/x.o" not in got and "build" not in got
    assert "src/a.py" in got and "docs/readme.md" in got


def test_path_pattern_and_separators():
    assert paths("-docs/*.md\n-build/") == ["src", "src/a.py", "src/b.tmp", "docs", "top.py"]


def test_include_and_exclude_combined():
    assert paths("*.py;*.tmp;-*.tmp") == ["src", "src/a.py", "top.py"]


def test_apply_to_report_recomputes_summary():
    rep = NS(entries=list(ENTRIES), summary=None)
    apply_to_report(rep, "*.py")
    assert rep.summary.total == 3 and rep.summary.different == 3
