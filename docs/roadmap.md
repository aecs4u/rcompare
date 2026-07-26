# Roadmap: remaining work for competitive parity

Last verified against source: 2026-07-25; §7 added 2026-07-26 from the Beyond
Compare configuration-surface study. Replaces `GAPS.md`, `ROADMAP.md`,
`ROADMAP_VFS.md`, and the forward-looking sections of the two dated CLI/GUI
milestone plans (all deleted this pass — see `CHANGELOG.md`). Competitor
baseline is [FEATURE_COMPARISON.md](../FEATURE_COMPARISON.md) (Beyond Compare,
WinMerge, Meld, KDiff3, P4Merge).

**Why this doc exists**: a source audit this pass found the previous
roadmap/gap docs wrong in both directions — some "done" items had regressed
or were never true, but more importantly several "planned"/"missing" items
were already built (archive write, RAR read, teczka tabs/drag-drop/3-way
merge/sync-preview). The single biggest pattern found: **real, tested
`rcompare_core` APIs that nothing in `rcompare_cli` or `teczka` calls.**
Wiring those up is cheaper and higher-value than any net-new feature below,
so this list leads with that.

Status legend: ✅ Done · 🔌 Built but unwired · 🚧 Partial · ❌ Missing.

## 1. Highest-value near-term work (wiring, not new features)

These are the fastest path to real parity gains — the engines already exist
and are tested; they're just not reachable from the CLI or GUI.

1. **Wire archive write (ZIP/TAR/7Z) into `rcompare_cli sync`/`copy` and
   teczka.** `WritableZipVfs`/`WritableTarVfs`/`Writable7zVfs` are done and
   tested in `rcompare_core::vfs::archive` but have zero callers outside
   their own tests. See [docs/modules/rcompare_core.md](modules/rcompare_core.md).
   Impact: high (this is table-stakes for BC/WinMerge-style archive sync).
2. **Wire `ResumableCopy` into `sync`/`copy`.** The checkpoint/resume engine
   in `rcompare_core::resumable_copy` (554 lines, tested) has zero callers
   from `rcompare_cli`. Impact: high — "resume interrupted sync" is currently
   listed as a Beyond Compare advantage in FEATURE_COMPARISON.md purely
   because of this wiring gap, not a missing capability.
3. **Wire cloud VFS (S3/SFTP/WebDAV) into CLI path parsing and teczka's path
   bar** (e.g. `s3://bucket/path`, `sftp://host/path`). All three backends
   are fully implemented in `rcompare_core::vfs` but unreachable from either
   frontend. Impact: high — "full remote source parity in desktop UI" is the
   #1 item Beyond Compare still wins on, and the gap is wiring, not code.
4. **Fix the three WebDAV bugs** before wiring it up per #3: digest auth
   silently falls back to Basic; PROPFIND parsing is substring search, not a
   real XML parser; `parse_date()` always returns `now()` so mtimes are never
   actually read from the server. See
   [docs/modules/rcompare_core.md](modules/rcompare_core.md). Impact:
   correctness bug, not just a gap — shipping this wired-but-unfixed would be
   worse than leaving it unwired.
5. **Wire Union/Filtered VFS** (`rcompare_core::vfs::virtual_vfs`) into CLI or
   GUI — real, tested, currently reachable only via direct core API use.
   Impact: medium.
6. ~~**Fix teczka's drag-and-drop >2-path truncation**~~ ✅ Done 2026-07-26
   (WI-5.6): the first two paths are still the ones compared, but the
   discarded ones are now named in the status bar.

## 2. rcompare_core (net-new)

| Item | Status | Impact |
|---|---|---|
| Connection pooling / retry+backoff for SSH & cloud backends | ❌ | Medium — needed before #3 above is production-ready at scale |
| Snapshot VFS | ❌ | Medium |
| SQLite-backed index for 1M+ file trees | ❌ | Medium — current in-memory HashMap model is fine up to ~100k files |
| ISO image read support | ❌ | Low |
| `.zst` (Zstandard) single-file compression | ❌ | Low — `.gz`/`.bz2`/`.xz` already work |
| RAR write support / password-protected RAR | ❌ | Low — read-only RAR already covers the common case |
| Additional cloud providers (GCS, Azure Blob, Dropbox, OneDrive) | ❌ | Low — S3/SFTP/WebDAV cover the common cases; niche vs. dedicated sync tools |
| Watch mode (continuous directory monitoring) | ❌ | Low |
| Semantic/AST-based diff (refactor-aware) | ❌ | Low/experimental |
| Git-repository VFS | ❌ | Low — dedicated VCS tools already cover this well |

## 3. rcompare_cli

| Item | Status | Impact |
|---|---|---|
| Structured progress streaming (`--progress-json`/`--ndjson`) | ❌ | Medium — needed for GUI/CI integration beyond the current terminal-only bar |
| Unified JSON schema v2 across commands | ❌ | Medium — each command currently versions its own `1.x` schema independently |
| Report export: HTML/Markdown/JUnit XML | ❌ | Medium — only JSON + human text exist; teczka's GUI has CSV export but there's no CLI equivalent |
| Resumable sync/copy checkpoints, transaction log | 🔌 engine exists, unwired | See §1.2 |
| Cancellation | 🚧 | Scan-level Ctrl+C works (`ctrlc` → `AtomicBool` → `scan_vfs_with_cancel`); no resumable checkpoint for interrupted sync/copy |

## 4. teczka (GUI)

| Item | Status | Impact |
|---|---|---|
| KDE/Plasma compliance | 🚧 ~40% (baseline was 5%, target ≥90%) | High — see [docs/KDE_COMPLIANCE.md](KDE_COMPLIANCE.md), single largest open GUI-quality gap. WS3 Shortcuts is now test-enforced; WS5 Desktop (0/17) and WS4 Dialogs (0/12) are untouched |
| Automated GUI test coverage | 🚧 improving (11 files, ~205 tests, `pytest-qt`) | Medium — shortcut collisions, filter state, visible shell, session/document lifecycle, Settings round-trip and contrast are covered. Merge view, sync/export/profile dialogs and screenshot regression are not (WI-6.6) |
| `MainWindow` structural refactor | ❌ 3,400 lines, 139 methods | High — Phase 6 of the development plan; the Phase 5 contracts above are the seams it should be extracted along |
| Palette-derived theming | 🚧 partial | High — the theme selector now works and applies at startup, but `resources/themes.py` still holds 390 hardcoded hex colours and zero `palette(...)` references (WI-7.1) |
| Syntax highlighting | ❌ no `QSyntaxHighlighter` | Medium (WI-7.3) |
| Merge-view source-pane colouring | ❌ only the output pane is tinted | Medium — the diff data is already computed; this is a rendering gap (WI-7.2) |
| Localizer adoption | ❌ `localizer.py` + 152 `.ftl` lines, zero call sites | Medium — adopt or delete (WI-7.7) |
| Cloud/archive-write sources reachable from GUI | 🔌 depends on §1.1/§1.3 | High |
| ~~Drag-and-drop >2-path handling~~ | ✅ Done 2026-07-26 | — |
| ~~EXIF differences shown in the image view~~ | ✅ Done 2026-07-26 (WI-5.5) | — |
| ~~Key-based CSV row alignment~~ | ✅ Done 2026-07-26 (WI-5.3) — `--csv-key` plus a GUI key selector | — |
| ~~Hidden widgets owning visible state~~ | ✅ Done 2026-07-26 (WI-5.7/5.9) | — |

Already done and should **not** be re-added to future gap lists without
re-verifying against source first: multi-tab sessions, session profiles,
sync-preview dialog, three-way merge UI (independent `difflib`-based line
diff, not just a display of the core engine's tree-level plan), synced
scrolling + gutter map, hex viewer, drag-and-drop (modulo the bug above). See
[docs/modules/teczka.md](modules/teczka.md).

## 5. Competitive gaps vs. named tools (from FEATURE_COMPARISON.md)

| Feature | Competitor | Status | Impact |
|---|---|---|---|
| Full remote-source parity in desktop UI | Beyond Compare | 🔌 — see §1.3 | High |
| Resume interrupted sync | Beyond Compare | 🔌 — see §1.2 | High |
| MP3/audio tag comparison | Beyond Compare | ❌ | Low — niche |
| Windows Registry comparison | Beyond Compare | ❌ | Low — Windows-only niche |
| Immediate production-grade 3-way merge UX | Beyond Compare / KDiff3 | 🚧 — teczka's merge view is real but young/undertested (§4) | Medium |

RCompare's differentiators that competitors lack (unchanged from
FEATURE_COMPARISON.md, still accurate): memory-safe Rust core, strong JSON
CLI automation, open-source auditability, native `.gitignore` handling.

## 6. Testing / CI

| Item | Status | Impact |
|---|---|---|
| Multi-platform CI for core/CLI test matrix | 🚧 Linux-only in `ci.yml`; Windows/macOS only exercised at release time (`release.yml`) | Medium |
| Property-based testing (`proptest`) | ❌ | Low |
| Fuzz testing (patch/CSV/etc. parsers) | ❌ | Low |
| teczka automated coverage | 🚧 — see §4 | Medium |

## 7. Configuration-surface parity vs. Beyond Compare

Added 2026-07-26 from a systematic study of what Beyond Compare 5.2.4 lets a
user *configure* — all 11 `Tools > Options` pages, the per-type Session
Settings dialogs and the File Formats editor. Evidence: 62 screenshots in
[`.playwright-mcp/bcompare/`](../.playwright-mcp/bcompare/); analysis in
[BCOMPARE_GUI_CONFIG_COMPARISON.md](BCOMPARE_GUI_CONFIG_COMPARISON.md);
sequencing in [development-plan.md](development-plan.md) Phase 9.

This is net-new scope, not repair — none of it is a defect. Roughly half needs
`rcompare_core`/CLI support before teczka can expose anything, marked below.

| Item | Side | Status | Impact |
|---|---|---|---|
| **File-format grammars + "ignore unimportant differences"** — 24 formats, each defining Keyword/Identifier/Number/String/Comment/Operator as regexes, plus line weights and an importance mask | core → CLI → GUI | ❌ | **High** — the largest single capability gap; it is why BC reports a comment-only change as *equal*. Shares a tokeniser with syntax highlighting (WI-7.3) — build once (WI-9.5) |
| **Settings scope selector** — "this view only" / session / defaults | GUI | ❌ | High — `SessionState` already stores per-tab settings; only the user-facing half is missing, and every other item here needs somewhere to live (WI-9.1) |
| **Comparison criteria** — timestamp tolerance (seconds), ignore DST, ignore timezone, filename case, Unicode normalisation alignment, Unix permissions/owner/group, CRC vs binary vs rules-based content compare | core → CLI → GUI | ❌ | High — teczka covers ~4 of BC's ~40 session settings. Timestamp tolerance alone removes false differences on FAT/exFAT and network filesystems (WI-9.2) |
| **Structured name filters** — include/exclude × files/folders as four independent lists, with reusable presets; plus rule-based size/date/attribute filters | core → CLI → GUI | ❌ | High — teczka has one flat `ignore_patterns` list. `.gitignore` handling stays a differentiator BC lacks (WI-9.3) |
| **Configurable text alignment** — Unaligned / Standard / Myers O(ND) / Patience Diff, skew tolerance, closeness matching; plus per-session replacements and folder-level alignment overrides | core → CLI → GUI | ❌ | Medium — Patience notably improves reordered-block output (WI-9.6) |
| **Table/CSV parsing controls** — delimiters, text qualifier, fixed-width, consecutive-delimiter handling, first-line-contains; Regional decimal/thousands separator and date order | core → CLI → GUI | ❌ | Medium — current fixed assumptions misparse Italian-locale data (`1.234,56`, DMY) (WI-9.7) |
| **Remote connection profiles** — named FTP/SFTP/SSH connections, SSH key and SSL certificate paths, per-profile ASCII masks | GUI, needs §1.3 | ❌ | Medium — the credential store the GUI's URL support requires; keyring only, never in `pyside.json` (WI-9.8) |
| **Workspaces** — a named set of open sessions, loaded/saved as a unit | GUI | ❌ | Medium — teczka has sessions and profiles but no grouping (WI-9.4) |
| **Global preferences parity** — File Operations confirmations, Backups, Next Difference, Startup, Tabs, Text Editing, Archive Types, Open With | GUI | ❌ | Medium — 8 of BC's 11 preference pages have no teczka counterpart. Each toggle needs a consumer before it ships (WI-9.9) |
| **Command customisation** — per-view menu placement, toolbar placement and shortcut | GUI | 🚧 shortcuts only | Low — shortcut persistence landed in Phase 5; placement control depends on whether a toolbar returns (WI-9.10) |
| **Settings portability** — export/import settings, restore factory defaults | GUI | ❌ | Medium — cheap on the existing JSON config; must exclude credentials (WI-9.11) |
| **View menu completions** — Columns (8 selectable fields), Legend, Suppress Filters, Log panel | GUI | ❌ | Low–Medium — Columns and Legend are near-free: column visibility/order already works and `color_legend.py` already exists (WI-9.12) |

Not surveyed, and therefore not scoped above: Session Settings for Folder
Merge, Folder Sync, Text Merge, Hex, Media and Picture Compare (they reuse the
Folder and Text Compare tab structures), and the contents of Table Compare's
Sheets/Columns/Rows tabs.

## Out of scope / intentionally deferred

Plugin/extension system, REST/gRPC API server, per-platform shell
integrations (Finder/Explorer/Nautilus extensions) — none started, all low
priority relative to the wiring work in §1. Not tracked further here unless
someone requests them.
