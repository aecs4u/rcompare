"""The single source of truth for folder-comparison filtering.

Before this existed, filter state lived in four places at once: a hidden
``FilterBar``, the View menu's check actions, the visible status-bar pills and
the per-session snapshot. They disagreed — the proxy defaulted to
``show_differences`` while every visible pill read "on", so the UI claimed
identical rows were shown while they were hidden.

Every input surface now reads and writes one :class:`FolderFilterState`, and
:meth:`MainWindow._apply_filter_state` is the only thing that pushes it out to
the proxy, the menu, the footer and the session.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# High-level presets exposed in View > Filter. ``custom`` is not selectable; it
# is what the state reports when the individual toggles match no preset.
PRESET_ALL = "all"
PRESET_DIFFS = "diffs"
PRESET_SAME = "same"
PRESET_CUSTOM = "custom"

DIFF_OPTION_MODES: tuple[str, ...] = (
    "show_all",
    "show_differences",
    "show_no_orphans",
    "show_differences_no_orphans",
    "show_orphans",
    "show_left_newer",
    "show_right_newer",
    "show_left_newer_left_orphans",
    "show_right_newer_right_orphans",
    "show_left_orphans",
    "show_right_orphans",
)

# The default must not contradict the visible controls. All four status pills
# start checked, so the diff-option mode has to be the one that shows every
# status; picking "show_differences" here is what used to hide identical rows
# while the Identical pill claimed to be on.
DEFAULT_DIFF_OPTION_MODE = "show_all"


@dataclass(frozen=True)
class FolderFilterState:
    """Immutable snapshot of every folder-view filter input."""

    show_identical: bool = True
    show_different: bool = True
    show_left_only: bool = True
    show_right_only: bool = True
    show_files_only: bool = False
    search_text: str = ""
    diff_option_mode: str = DEFAULT_DIFF_OPTION_MODE

    # -- Derived state --------------------------------------------------

    @property
    def preset(self) -> str:
        """Return which View > Filter preset the status toggles correspond to."""
        flags = (
            self.show_identical,
            self.show_different,
            self.show_left_only,
            self.show_right_only,
        )
        if flags == (True, True, True, True):
            return PRESET_ALL
        if flags == (False, True, True, True):
            return PRESET_DIFFS
        if flags == (True, False, False, False):
            return PRESET_SAME
        return PRESET_CUSTOM

    # -- Transformations ------------------------------------------------

    def with_preset(self, preset: str) -> FolderFilterState:
        """Return a copy with the status toggles set from a preset name.

        Only the four status toggles change; files-only, search text and the
        diff-option mode are deliberately preserved, because a preset click is
        not a request to reset unrelated filters.
        """
        if preset == PRESET_ALL:
            return replace(
                self,
                show_identical=True,
                show_different=True,
                show_left_only=True,
                show_right_only=True,
            )
        if preset == PRESET_DIFFS:
            return replace(
                self,
                show_identical=False,
                show_different=True,
                show_left_only=True,
                show_right_only=True,
            )
        if preset == PRESET_SAME:
            return replace(
                self,
                show_identical=True,
                show_different=False,
                show_left_only=False,
                show_right_only=False,
            )
        return self

    def with_statuses(
        self,
        identical: bool,
        different: bool,
        left_only: bool,
        right_only: bool,
    ) -> FolderFilterState:
        """Return a copy with only the four status toggles replaced.

        Notably this does *not* touch ``show_files_only``. Clicking a status
        pill used to silently turn files-only mode on, hiding every folder row.
        """
        return replace(
            self,
            show_identical=identical,
            show_different=different,
            show_left_only=left_only,
            show_right_only=right_only,
        )

    def with_search(self, text: str) -> FolderFilterState:
        return replace(self, search_text=text)

    def with_files_only(self, files_only: bool) -> FolderFilterState:
        return replace(self, show_files_only=files_only)

    def with_diff_option_mode(self, mode: str) -> FolderFilterState:
        normalized = (mode or DEFAULT_DIFF_OPTION_MODE).strip().lower()
        if normalized not in DIFF_OPTION_MODES:
            normalized = DEFAULT_DIFF_OPTION_MODE
        return replace(self, diff_option_mode=normalized)

    # -- Serialisation --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "show_identical": self.show_identical,
            "show_different": self.show_different,
            "show_left_only": self.show_left_only,
            "show_right_only": self.show_right_only,
            "show_files_only": self.show_files_only,
            "search_text": self.search_text,
            "diff_option_mode": self.diff_option_mode,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> FolderFilterState:
        data = data or {}
        mode = data.get("diff_option_mode", DEFAULT_DIFF_OPTION_MODE)
        if not isinstance(mode, str) or mode.strip().lower() not in DIFF_OPTION_MODES:
            mode = DEFAULT_DIFF_OPTION_MODE
        search = data.get("search_text", "")
        return cls(
            show_identical=bool(data.get("show_identical", True)),
            show_different=bool(data.get("show_different", True)),
            show_left_only=bool(data.get("show_left_only", True)),
            show_right_only=bool(data.get("show_right_only", True)),
            show_files_only=bool(data.get("show_files_only", False)),
            search_text=search if isinstance(search, str) else "",
            diff_option_mode=mode.strip().lower(),
        )
