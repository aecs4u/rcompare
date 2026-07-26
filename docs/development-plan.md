# Development Plan

Created: 2026-07-25. Initial source review at commit `c17ea5d`; the runtime
design-review addendum was verified against the 2026-07-25 working tree.

**Scope authority**: [FEATURE_COMPARISON.md](../FEATURE_COMPARISON.md) defines
*what* parity means; [roadmap.md](roadmap.md) is the maintained list of *what's
left*. This document is neither — it is the **execution plan**: how the
remaining work is sequenced into shippable increments, what each increment
touches, and how we know it's done. When scope changes, update `roadmap.md`;
when sequencing changes, update this file.

## The central finding that shapes this plan

`FEATURE_COMPARISON.md` lists five capabilities as 🔌 "engine exists, not
wired" (archive write, cloud VFS, resumable copy, union VFS, plus GUI reach for
the same). These are not five independent tasks. They share **one** blocker:

```
rcompare_cli/src/commands/sync.rs:64    if !left.is_dir() || !right.is_dir() { ... "local directory paths only" }
rcompare_cli/src/commands/copy.rs:44    if !left.is_dir() || !right.is_dir() { ... "local directory paths only" }
rcompare_cli/src/commands/support.rs    apply_copy / copy_dir_recursive / apply_delete — all std::fs, all &Path
```

`scan` already reads through a `Vfs` (`ScanSource::Vfs`, `support.rs:451`), but
`sync`/`copy` **write** through bare `std::fs`. Every unwired backend is a
write target. So the highest-leverage single change in the entire backlog is
giving the mutation path the same VFS abstraction the read path already has —
after which archive-write, S3, SFTP, WebDAV and union sources all become
configuration rather than features.

The good news: `rcompare_common::Vfs` already declares the full write surface
(`create_file`, `create_dir_all`, `rename`, `set_mtime`, `write_file`, `flush`,
`is_writable`, `capabilities`). No core-side trait work is required.

Accordingly the plan front-loads Phase 1, and everything else is scheduled
around it.

The same pattern recurs in the GUI. The teczka design review found **EXIF
comparison** and **key-based CSV row alignment** both implemented in
`rcompare_core`, reachable from the CLI, and invisible in teczka — bringing
the built-but-unwired count to six. Treat "wire what exists" as this
project's default posture rather than a one-off phase.

Both GUI instances are now closed (Phase 5, 2026-07-26): the image view renders
EXIF differences, and `--csv-key` plus a GUI key selector expose
`CsvDiffEngine::with_key_columns`. The four engine-side items (archive write,
cloud VFS, resumable copy, union VFS) remain, and Phase 1 is still their
single blocker.

## Already completed (2026-07-25)

Fixed while reviewing, so they are not scheduled below: teczka's permanently
stuck "Comparing..." status bar, clipped path breadcrumbs, the hex view's
bottom-pinned layout, the unconditional welcome-dialog launch gate, the
missing path-bar folder picker (now portal/native, reaching desktop-mounted
network locations), and the forced Fusion widget style. See `CHANGELOG.md`
`[Unreleased]`.

The runtime addendum below distinguishes the repaired comparison-completion
summary from the operation messages and progress state that still need to be
migrated into the visible shell under WI-5.7.

---

## Phase overview

| Phase | Theme | Gates | Est. |
|---|---|---|---|
| 0 | Preconditions & correctness debt | — | 3–5 d |
| 1 | VFS-aware mutation path (the unlock) | P0 | 8–13 d |
| 2 | Backend wiring on top of Phase 1 | P1 | 7–11 d |
| 3 | Resumable sync/copy | P1 | 4–6 d |
| 4 | CLI automation surface (v2) | P1 (loosely) | 8–12 d |
| 5 | teczka: correctness & contract | — | ✅ done 2026-07-26 |
| 6 | teczka: structural refactor | P5 (test net) | 15–20 d |
| 7 | teczka: presentation, accessibility & KDE compliance | — | 22–30 d |
| 8 | Scale & net-new core | P2 | opportunistic |
| 9 | Beyond Compare configuration parity | P5; WI-9.5/9.6 gate WI-7.3 | 30–45 d |

Phase 9 is the newest tier, added from the 2026-07-26 configuration-surface
study. It is deliberately last: it is net-new capability rather than repair,
and roughly half of it needs `rcompare_core`/CLI work before teczka can expose
anything. Two cross-references matter — **WI-9.5** (grammar/rules engine)
shares its tokeniser with **WI-7.3** (syntax highlighting), so those should
land together rather than building two lexers; and **WI-9.8** (connection
profiles) depends on **WI-2.1** for the URL schemes it stores.

Phases 5–7 are independent of engine Phases 1–4. Within the GUI track, Phase 5
makes visible controls authoritative before Phase 7 reshapes them; palette,
icon and early accessibility work can still run in parallel. Phase 6 depends
on its own test scaffolding (WI-6.1). Phases 2 and 3 are strictly downstream
of Phase 1.

**One cross-phase ordering constraint:** **WI-5.2** (validate the CLI schema
version in teczka) must land before **WI-4.1** (unified JSON schema v2), or
schema v2 breaks the GUI with a `KeyError` in a worker thread. It is the only
hard dependency between the Rust and Python tracks.

---

## Phase 0 — Preconditions and correctness debt

Small, unblocking, and mostly cleanup. Do this first because Phase 2 must not
ship WebDAV in its current state.

### WI-0.1 — Fix the three WebDAV correctness bugs
**Files**: [rcompare_core/src/vfs/webdav.rs](../rcompare_core/src/vfs/webdav.rs)

Three real defects, all confirmed in source:

1. **`parse_date()` (webdav.rs:165) ignores its argument entirely** and returns
   a `now()`-based value, so every remote mtime is wrong. This silently
   corrupts any timestamp-based comparison or `newest`-conflict-policy sync —
   the most dangerous of the three. Fix: parse RFC 1123 (`getlastmodified`) and
   ISO 8601 (`creationdate`) via `chrono`, return `None` on failure rather than
   fabricating a time.
2. **Digest auth silently degrades to Basic** (webdav.rs:117 and again at
   webdav.rs:545). Credentials configured as Digest go out as Basic over
   whatever transport is in use. Fix: implement the digest challenge/response
   handshake, or — the acceptable interim — return a hard configuration error
   instead of downgrading. Never downgrade silently.
3. **PROPFIND parsing is `str::find` substring scanning** (webdav.rs:129–250),
   which breaks on namespace prefixes other than `D:`, on attributes, and on
   any non-line-oriented server response. Fix: parse with `quick-xml`,
   namespace-aware.

**Acceptance**: unit tests over recorded PROPFIND bodies from at least two
servers with differing namespace prefixes; a test asserting a Digest-configured
client never emits a `Basic` header; a test asserting mtime round-trips from
a fixture body rather than tracking wall-clock.

### WI-0.2 — Remove the empty `rcompare_gui/` directory
It is not a workspace member (`Cargo.toml` lists four crates) and contains
nothing, but its presence contradicts the docs that say the Slint GUI was
removed. One-line cleanup; prevents recurring "is this still a thing?" churn.

### WI-0.3 — *(moved)*
teczka's drag-and-drop truncation is now **WI-5.6**, with the rest of the GUI
correctness work.

### WI-0.4 — Multi-platform CI matrix
**File**: `.github/workflows/ci.yml`

Currently Linux-only; Windows/macOS are exercised only at release time, which
means cross-platform breakage is discovered at the worst possible moment. Add
`windows-latest` and `macos-latest` to the core/CLI test matrix. Do this before
Phase 1 so the VFS path-handling rewrite (separators, UNC, case sensitivity) is
validated on all three targets as it lands.

---

## Phase 1 — VFS-aware mutation path *(the unlock)*

This is the plan's keystone. Everything in Phases 2, 3 and part of 5 is blocked
on it.

### WI-1.1 — Introduce a `SyncTarget` write handle
**Files**: `rcompare_cli/src/commands/support.rs` (new module recommended:
`commands/target.rs`)

Mirror the existing read-side `ScanSource` enum with a write-side counterpart
that owns either a local root or a `Box<dyn Vfs>` root, and route all mutation
through it:

- `apply_copy(&Path, &Path)` → `apply_copy(&SyncTarget, rel, &SyncSource, rel)`
- `copy_dir_recursive` → VFS-generic recursive walk
- `apply_delete(&Path, DeleteMode)` → `apply_delete(&SyncTarget, rel, DeleteMode)`

Trash semantics are local-only by definition. `DeleteMode::Trash` against a
non-local target must fail with an explicit error naming the reason — not fall
back to permanent deletion. This is a data-loss-shaped decision; make it loud.

### WI-1.2 — Capability negotiation and preflight
**Files**: `commands/target.rs`, `commands/sync.rs`, `commands/copy.rs`

`Vfs::capabilities()` and `is_writable()` already exist and are unused by the
CLI. Before executing any plan, check the target supports every operation the
plan needs, and fail with a single actionable message listing the unsupported
operations — rather than discovering it halfway through a 40 GB sync. Surface
the same information through `rcompare capabilities`.

### WI-1.3 — Replace the `is_dir()` gates
**Files**: `sync.rs:64`, `copy.rs:44`

Swap the hard local-dir precondition for source/target resolution. Keep the
error message quality: an unreachable `s3://` bucket should say so, not
degrade to "not a directory".

### WI-1.4 — Test scaffolding for VFS mutation
**Files**: `rcompare_cli/tests/`

`cli_scan.rs` already constructs `WritableZipVfs`/`WritableTarVfs`/
`Writable7zVfs` fixtures — extend that pattern into sync/copy integration
tests. Cover: local→archive, archive→local, local→local regression, and a
read-only-target rejection. This suite is the safety net for Phase 2.

**Phase 1 acceptance**: `sync` and `copy` behave identically to today for
local↔local (no regressions in the existing suite), and a ZIP target is a
legal, tested sync destination.

---

## Phase 2 — Backend wiring

Each item is now small because Phase 1 did the structural work.

### WI-2.1 — URL-scheme path parsing
**File**: `support.rs:451` (`build_scan_source`)

Today the resolver handles local dirs and archives-by-extension only. Add
scheme dispatch: `s3://bucket/prefix`, `sftp://user@host/path`,
`dav(s)://host/path`, `zip:///abs/path.zip!/inner`. One parser, shared by
source and target resolution, so `rcompare sync ./local s3://bucket/backup`
works without per-command special-casing.

Credentials: environment/config-file only. Do not accept secrets as CLI
arguments — they leak into shell history and process listings.

### WI-2.2 — Archive write targets
`WritableZipVfs::create`/`WritableTarVfs::create`/`Writable7zVfs::create` are
tested and callerless. Wire into target resolution: an archive path as sync
destination creates or updates in place. Note the atomicity constraint —
`WritableZipVfs` rewrites the container; document that an interrupted archive
sync leaves the original intact (verify this holds, and if it doesn't, write
via temp-file-plus-rename).

### WI-2.3 — Cloud targets (S3 → SFTP → WebDAV)
Land in that order: S3 has the most tests (`tests_cloud.rs`, 1785 lines), SFTP
is simplest, WebDAV goes last and only after WI-0.1. Each gets an integration
test against a local mock/container.

### WI-2.4 — Connection pooling, retry, backoff
**Files**: `rcompare_core/src/vfs/{s3,sftp,webdav}.rs`

Per-operation connection setup is fine at test scale and pathological at tree
scale. Add a shared pool plus exponential backoff with jitter on retryable
errors. Roadmap correctly marks this as a prerequisite for calling WI-2.3
production-ready — treat it as part of Phase 2, not a follow-up.

### WI-2.5 — Union/Filtered VFS reach
Expose `UnionVfs`/`FilteredVfs` via repeatable `--overlay <path>` on `scan`.
Smallest item here; medium value; do it last in the phase.

---

## Phase 3 — Resumable sync/copy

### WI-3.1 — Wire `ResumableCopy` into `copy`
**Files**: `rcompare_core/src/resumable_copy.rs` (554 lines, tested, zero
callers), `commands/copy.rs`

`ResumableCopy::copy_resumable` (resumable_copy.rs:132) plus
`CopyCheckpoint::{save,load,delete}` are ready. Add `--resume` /
`--checkpoint-dir`, default checkpointing on for transfers above a size
threshold.

### WI-3.2 — Extend to `sync`
Sync needs a plan-level checkpoint (which actions completed), not just a
per-file one. Persist the action list at plan time, mark entries complete as
they execute, and on `--resume` re-validate that the source hasn't changed
underneath before continuing.

### WI-3.3 — Ctrl+C → checkpoint
Cancellation currently works at scan level only (`ctrlc` → `AtomicBool` →
`scan_vfs_with_cancel`). Extend the same flag into the mutation loop so
interrupts flush a checkpoint instead of dropping progress.

### WI-3.4 — Checkpoint GC
`cleanup_checkpoints` (resumable_copy.rs:383) exists and is uncalled. Run it on
successful completion and expose `rcompare sync --clean-checkpoints`.

**Acceptance**: an integration test that kills a copy mid-transfer, resumes,
and byte-compares the result against a clean run. This closes the last row of
FEATURE_COMPARISON.md's sync table where Beyond Compare currently wins.

---

## Phase 4 — CLI automation surface

Independent of Phases 1–3; this is where RCompare's stated differentiator
(machine-readable output) is extended.

### WI-4.1 — JSON schema v2
Each command versions its own `1.x` schema independently today. Define one
envelope — `{schema_version, command, status, summary, data, warnings}` — and
publish JSON Schema files under `docs/schemas/`. Keep v1 emitting under
`--schema-version 1` for one release cycle, then deprecate.

### WI-4.2 — Structured progress streaming
`--progress-json` / `--ndjson` emitting scan/compare/sync events to stderr
while results go to stdout. This is the prerequisite for teczka driving the CLI
without screen-scraping, and for CI progress reporting.

### WI-4.3 — Report export
HTML, Markdown, and JUnit XML writers for scan/sync results. JUnit XML is the
highest-value of the three: it makes `rcompare scan` a first-class CI gate.
teczka already has CSV export — reuse its column model for consistency.

---

## Phases 5–7 — teczka

Derived from
[history/TECZKA_DESIGN_REVIEW.md](history/TECZKA_DESIGN_REVIEW.md) (2026-07-25),
a runtime-verified architecture/UX review benchmarked against Beyond Compare
5.2.4. Section references below (§2.2, §2.6, …) point into that document for
the evidence behind each item.

The review's own conclusion drives the ordering: teczka's problems are
**concentrated, not diffuse**. One 3,400-line class holds logic that belongs
elsewhere; two subsystems are built but inert; the contract with the CLI is
unvalidated. The view layer is healthy and should not be rewritten.

Split into three tiers because they have genuinely different risk profiles:
Phase 5 is small and safe, Phase 6 is invasive and needs the test net built
first, and Phase 7 contains presentation/accessibility work that can mostly be
parallelised once Phase 5 has made the visible controls authoritative.

### Runtime design-review addendum (2026-07-25)

A second, full product-design pass rendered Home, Folder, Text, Image, Table,
Splash, Settings and Merge at desktop size, with the Home view repeated at the
declared 800×600 minimum and Folder repeated under a forced dark palette. It
also exercised live session closing, path swapping, shortcut resolution,
view-stack navigation, theme application and filter state. The review combined
rendered-state inspection, keyboard traversal, widget-tree interrogation and
source tracing; findings below are therefore confirmed behaviour, not a
mock-up critique.

The resulting product-design assessment is **4.5/10 overall**: the comparison
engines and redesigned Folder surface are credible, but the shell cannot yet
be considered trustworthy because visible controls, hidden state and
operation feedback disagree. The recent visual redesign is ahead of the
application state architecture: the visible shell coexists with hidden
compatibility widgets that still own behaviour.

### Measured design baseline

These numbers are point-in-time regression markers, not targets:

| Measure | Verified value | Design implication |
|---|---:|---|
| `MainWindow` size | 3,407 lines, 139 methods, 73 `_on_*` slots | UI construction, navigation, persistence and operations have no enforceable boundaries |
| Actions in the live window | 121 | Action scope and shortcut correctness need automated checks |
| Calls to hidden native status messaging | 49 | Routine operation feedback is invisible |
| Modal `QMessageBox` uses in the main/dialog/view surfaces | 67 | Non-fatal feedback is overly interruptive |
| Explicit accessible names in the app | 2, both in Splash | Icon-only and custom controls are largely opaque to assistive technology |
| Initial view stack / sidebar destinations | 6 / 7 | The visible 3-Way destination is inert |

The four visible folder-status pills also fail WCAG contrast for normal text:
green **2.78:1**, red **3.63:1**, blue **3.59:1**, and right-only red
**3.76:1**, all below **4.5:1**. In the unchecked state, foreground and
background both resolve to `palette(mid)`, making the label effectively
invisible. Treat these values as test fixtures for WI-7.12 rather than merely
visual preferences.

The verified findings are mapped into work items below:

| Severity | Finding | Scheduled in |
|---|---|---|
| Blocker | Visible session tabs cannot close; dynamic file comparisons are registered in a hidden tab bar; 3-Way Merge is advertised but unreachable | WI-5.8, WI-7.5 |
| Blocker | Visible filters disagree with actual results; menu filters update hidden state; status-pill interaction silently enables files-only mode; `Ctrl+F` focuses a hidden field | WI-5.9 |
| Blocker | Most operation messages and progress updates target a hidden status bar/progress widget; visible progress and `0/0` navigation do not update | WI-5.7 |
| Blocker | Path-bar Swap swaps twice and produces no change | WI-5.11 |
| Blocker | Light/Dark and CLI-path settings are exposed but discarded through the connected Preferences handler; neither theme stylesheet is applied at startup | WI-5.10, WI-7.1 |
| Blocker | Diff/Files settings expose whitespace, case, specialised comparison, regex, encoding, EOL and binary-pattern controls that are neither returned, persisted nor applied | WI-5.10 |
| Blocker | Sync Preview promises a later confirmation, but Execute starts mutation immediately; permanent deletion has no distinct second confirmation | WI-7.14 |
| High | Home profile activation is unconnected and reads a different store from `ProfileManager`; recent sessions are rendered but never populated | WI-5.8, WI-7.11 |
| High | Home content clips at 800×600; specialist views have weak empty states; fixed dimensions are fragile under font scaling/localisation | WI-7.11 |
| High | Folder filters and folder paths remain visible in unrelated Text/Image/Hex/Table/Home contexts | WI-7.13 |
| High | Keyboard conflicts (`Ctrl+P`, `Ctrl+Y`) and non-functional Find behaviour | WI-5.1, WI-5.9 |
| High | Core controls are removed from keyboard focus; unchecked filter labels have no contrast; status relies primarily on colour | WI-7.12 |
| High | Theme icons have no fallback in Home/sidebar/settings, producing blank navigation and cards when a FreeDesktop icon theme is absent | WI-7.4, WI-7.12 |
| Medium | Folder, Text, Hex, Image, Table and Merge use different pane headers, toolbars, empty states and colour semantics | WI-7.1, WI-7.13 |
| Medium | Home's “New Session” cards only switch modes and omit Table/Merge; sidebar expansion exists without an invocation | WI-7.5, WI-7.11 |
| Medium | “Configure Toolbars…” is a placeholder after the toolbar was removed; KDE-only and product-name labels are unconditional/inconsistent | WI-7.15 |
| Medium | “Changed” and “Applied” colour settings are exposed but not consumed by TextView | WI-5.10 |

The folder comparison view remains the strongest surface: its pane hierarchy,
breadcrumb paths, independent selectable columns and persisted header layouts
are the reference quality bar. Preserve those behaviours while consolidating
the shell around them.

### Surface-by-surface target state

This matrix carries the complete screen review into implementation rather than
leaving it as general “polish”:

| Surface | Keep | Required improvement |
|---|---|---|
| Global shell | Compact rail, session strip and integrated footer direction | Make chrome contextual; expose one document model; remove hidden state owners; show messages/progress/diff position in the visible footer |
| Home | Clear task-launcher intent and recent/profile sections | Responsive scrollable layout; Folder/Text/Hex/Image/Table/Merge coverage; connect profile activation to `ProfileManager`; populate recents; provide explicit Open affordances |
| Folder | Strong split-pane hierarchy, breadcrumbs and selectable persisted columns | Blank opposite-side gaps for orphan rows; visible status marker; semantic theme colours; metadata strip; discoverable filter/expand/collapse/swap/refresh |
| Text | Effective side-by-side and intra-line comparison | Remove folder-only chrome; add file metadata, contextual search/edit/save/navigation, syntax highlighting and less oppressive full-line red/green fills |
| Hex | Correct byte/ASCII comparison | Add search, go-to-offset, selection details and contextual diff navigation |
| Image | Useful side-by-side image and basic metrics | Add synchronised pan/zoom, overlay/difference modes, responsive statistics and EXIF differences |
| Table | Useful cell-level comparison | Add key-based alignment, header/schema controls, column selection/reordering and explicit left-only/right-only row treatment |
| Merge | Sound four-pane structure and resolution actions | Highlight conflict regions in all source panes; group resolution controls; provide narrow-width overflow and clear unresolved-state feedback |
| Settings | Understandable category structure | Persist and apply every exposed field, validate CLI path, make theme live, remove controls with no consumer, remain readable under scale/localisation |
| Dialogs/feedback | Errors are consistently surfaced | Replace routine modal alerts with visible non-modal feedback; use specific destructive labels; make Sync Preview a structured plan with an unambiguous confirmation boundary |

### Product-wide design principles established by the review

1. **Visible state is authoritative.** No hidden widget may own navigation,
   filters, progress, persistence or command state.
2. **One concept has one source of truth.** Paths, filters, active document,
   theme and session state must not have parallel widget and model copies.
3. **Context determines chrome and actions.** Folder controls do not appear in
   Text/Image/Hex/Table/Merge; unsupported commands are disabled and explain
   why.
4. **Safety language matches execution.** “Preview”, “dry run”, “execute” and
   “permanent delete” describe distinct states, with consent at the actual
   mutation boundary.
5. **Status is semantic, not colour-only.** Every diff state has text or an
   icon/shape, a palette-aware colour and tested contrast.
6. **The supported minimum is real.** 800×600 and 125–200% scaling are release
   checks, not aspirational dimensions.

### Beyond Compare configuration-surface study (2026-07-26)

A third pass, distinct from the two above: rather than benchmarking teczka's
*rendered screens*, it enumerated **what Beyond Compare lets a user configure**.
Every menu, all 11 `Tools > Options` pages, the per-type Session Settings
dialogs and the File Formats editor were opened in Beyond Compare 5.2.4 (build
32425) under Linux/Qt and captured via XTEST automation.

Evidence: **62 screenshots** in
[`../.playwright-mcp/bcompare/`](../.playwright-mcp/bcompare/) — `options_*`
(all 11 preference pages), `fc_*` (Folder Compare menus, submenus, 6 Session
Settings tabs), `tc_*` (Text Compare menus, 5 Session Settings tabs), `tbc_*`
(Table Compare menus, Table Format tabs), `home_*`, `tools_file_formats*`.
Full analysis in
[BCOMPARE_GUI_CONFIG_COMPARISON.md](BCOMPARE_GUI_CONFIG_COMPARISON.md).

Not captured, and therefore not costed below: Session Settings for Folder
Merge, Folder Sync, Text Merge, Hex, Media and Picture Compare (they reuse the
Folder and Text Compare tab structures), and the contents of Table Compare's
Sheets/Columns/Rows tabs.

**This study does not overlap the design review.** The review asked whether
teczka's controls tell the truth — a question Phase 5 answered. This one asks
what controls exist *at all*, and the answer reorders part of the backlog:

| Finding | Why it matters | Scheduled in |
|---|---|---|
| **File Formats is a rules engine**, not a file-type list: 24 formats, each with a Grammar tab defining Keyword/Identifier/Number/String/Comment/Operator as regexes, plus line weights with priorities | This is what powers "Ignore Unimportant Differences" — a headline BC capability with no teczka or `rcompare_core` equivalent at any layer. Larger than the single ❌ row it occupied in FEATURE_COMPARISON.md | WI-9.5 |
| **Settings apply at a chosen scope** — "Use for this view only" / session / defaults | teczka stores settings per tab in `SessionState` but exposes no scope control, so every change is global. The storage exists; the user-facing half does not | WI-9.1 |
| **Comparison criteria are far richer**: timestamp tolerance in seconds, ignore DST, ignore timezone, filename case, align differing extensions, Unicode normalisation forms, Unix permissions/owner/group, and CRC vs binary vs rules-based content compare | teczka's `ComparisonSettings` covers roughly 4 of ~40 session-level settings. Timestamp tolerance alone is the most likely cause of false differences across filesystems | WI-9.2 |
| **Name filters are four independent lists** (include/exclude × files/folders) with reusable presets, plus a separate rule-based Other Filters tab (size/date/attribute) | teczka has one flat `ignore_patterns` glob list | WI-9.3 |
| **Text alignment is configurable**: Unaligned / Standard / Myers O(ND) / Patience Diff, skew tolerance, closeness matching — plus per-session Replacements and Alignment overrides | teczka's alignment is fixed | WI-9.6 |
| **Table parsing is configurable**: delimiters, text qualifier, fixed vs delimited, "first line contains", decimal/thousands separators, date order/separator | teczka's table view assumes CSV defaults | WI-9.7 |
| **`Tools > Profiles` is remote-connection config** (FTP/SFTP/SSH; Global/Server/Connection/Proxy/Listings/Transfer), *not* saved comparison setups | Corrects an earlier assumption. This is the credential-management surface WI-7.9 needs and currently lacks | WI-9.8 |
| **Workspaces** group multiple sessions and load/save as a unit | teczka has sessions but no workspace concept | WI-9.4 |
| Global preferences teczka has no equivalent for: Startup, Tabs, Text Editing, Next Difference, Backups, File Operations confirmations, Archive Types, Open With, Tweaks | 8 of BC's 11 preference pages have no teczka counterpart | WI-9.9 |
| **Commands page** assigns menu placement, toolbar placement and shortcut per command, per view | teczka's Configure Shortcuts covers only the shortcut third | WI-9.10 |
| Export / Import Settings and Restore Factory Defaults | teczka has a per-dialog Defaults button only; no portability | WI-9.11 |
| View menu items with no teczka equivalent: Ignore Unimportant Differences, Suppress Filters, Columns (8 selectable fields), Legend, Log panel | Columns and Legend are the cheap ones — `folder_columns` already persists widths and `color_legend.py` already exists | WI-9.12 |

Phase 5's Settings work is confirmed delivered against this study: `--cache-dir`
now reaches the worker, `AppConfig.shortcuts` persists rebindings, and the Files
page's encoding/EOL/binary-pattern values are consumed by the views. No
regression items are carried forward.

---

## Phase 5 — teczka correctness and contract

**Status: complete (2026-07-26).** All eleven work items landed with tests;
see `CHANGELOG.md` `[Unreleased]`. The suite grew from 38 to 205 `pytest-qt`
tests, and the contracts below are now enforced rather than reviewed:

| Item | Enforcing test |
|---|---|
| WI-5.1 shortcuts | `tests/test_shortcuts.py` — collision walk, standard-key resolution, generated About table |
| WI-5.2 schema contract | `tests/test_settings_roundtrip.py` — version mismatch names both versions |
| WI-5.3 CSV key alignment | `tests/test_workers_and_views.py` — positional vs. keyed summaries differ as documented |
| WI-5.4 worker cancel | `tests/test_workers_and_views.py` — a cancelled worker never delivers a result |
| WI-5.5 EXIF | `tests/test_workers_and_views.py` — local and CLI-fed difference tables |
| WI-5.6 drag-drop | `tests/test_workers_and_views.py` — discarded paths are named |
| WI-5.7 visible shell | `tests/test_visible_shell.py` — includes an AST check rejecting new `statusBar()` writes |
| WI-5.8 lifecycle | `tests/test_session_lifecycle.py` — sessions, documents, Merge reachability, Home |
| WI-5.9 filter state | `tests/test_filter_state.py` — state matrix across proxy, menu, footer, session |
| WI-5.10 Settings | `tests/test_settings_roundtrip.py` — restart round-trip for every field |
| WI-5.11 swap/actions | `tests/test_session_lifecycle.py` — one swap per click, enablement matrix |

Two Phase 7 items were absorbed opportunistically because Phase 5 touched the
same code: the status-pill contrast/focus/marker fixes from **WI-7.12** and the
responsive Home layout from **WI-7.11**. Both remain open overall — only the
folder-status pills and Home have been audited.

Original scope follows.

Small, independent, each verifiable. Nothing here needs the refactor.

### WI-5.1 — Fix the keyboard surface (§2.6) ✅
Three separate defects, all verified by walking the live menu tree:

1. **`Ctrl+Q` does not quit.** `main_window.py:227` uses
   `QKeySequence.StandardKey.Quit`, which resolves on Linux to the `Exit`
   multimedia key. Same trap on `StandardKey.Preferences` → `Settings`. Add an
   explicit fallback: use the standard key **only if** it produces a
   non-empty, non-multimedia binding, else hardcode `Ctrl+Q` / `Ctrl+,`.
2. **`Ctrl+P` collides** — Print (`StandardKey.Print`, correct) vs. Profiles
   (hardcoded). Rebind Profiles.
3. **`Ctrl+Y` collides** — Redo (`StandardKey.Redo` includes `Ctrl+Y`) vs.
   Synchronize (hardcoded). Rebind Synchronize.
4. **About documents stale shortcuts** — its keyboard table advertises
   `Ctrl+N` for the live `Ctrl+T` action and `Ctrl+Q` while the live binding is
   `Exit`. Generate that table from the action registry or test it against the
   live shortcuts rather than maintaining a second handwritten source.

**Acceptance**: a test that walks the menu tree, asserts no duplicate key
sequence, asserts Quit/Preferences resolve to real chords, and verifies the
About shortcut table matches the actions. This test is the point of the item —
without it the collisions recur. Update the Collision-Free row in
`KDE_COMPLIANCE.md` when it passes.

### WI-5.2 — Validate the CLI schema contract (§2.4) ✅
`rcompare_cli` emits `{"schema_version":"1.1.0", …}`; `utils/cli_bridge.py`
never reads it and parses by direct subscripting (`data["summary"]["total"]`),
so drift surfaces as a `KeyError` inside a worker thread.

Check the version at the boundary, accept a declared major range, and fail with
a message naming both the expected and received versions.

**Sequencing note:** this is a prerequisite for **WI-4.1 (JSON schema v2)**.
Landing schema v2 first breaks the GUI with a stack trace. Do this one before
Phase 4 reaches WI-4.1, regardless of the phase numbering.

### WI-5.3 — Key-based CSV row alignment (§1, "Algorithmic limitation") ✅
`rcompare_core/src/csv_diff.rs:201-204` aligns rows positionally
(`for i in 0..max_rows`), so a left-only and a right-only row get paired and
reported as "different", and the summary reports "0 left-only, 0 right-only" —
wrong output, not just a limitation. One inserted row cascades through the
whole file.

`CsvDiffEngine::with_key_columns()` (`csv_diff.rs:94`) already implements the
fix and has zero callers. Expose it: a `--csv-key <col>` CLI flag plus a key
selector in teczka's table view. Pair with a "first row is header" toggle,
which also retires the hardcoded `Col 1/2/3` labels at `table_view.py:381`
and `:466`.

Impact: this is the only item in Phase 5 that fixes *incorrect output* rather
than an ergonomic defect. Rank it first if time is short.

### WI-5.4 — Cancellation for `FunctionWorker` (§2.8) ✅
`workers/function_worker.py` subclasses `QThread` with no cancellation path —
long parses can only be orphaned, not interrupted. Add a cooperative cancel
flag checked between work units, and call it from the existing cancel action.

### WI-5.5 — Wire EXIF comparison into the image view (§1) ✅
`rcompare_core::image_diff` implements `ExifMetadata`/`exif_differences` and
the CLI exposes `--image-exif`, but `views/image_view.py` never requests or
displays it. Wire the existing flag through and render the differences table.
Then restore the `FEATURE_COMPARISON.md` EXIF row to ✅.

### WI-5.6 — Drag-and-drop >2-path truncation ✅
Previously WI-0.3. `dropEvent` keeps the first two dropped paths and discards
the rest silently; use the first two **and** say so in the status bar.

### WI-5.7 — Make the visible shell authoritative ✅
**Files**: `teczka/main_window.py`,
`teczka/widgets/integrated_status_bar.py`

The modern shell creates a visible `SessionTabBar`, `CompactPathBar` and
`IntegratedStatusBar`, then creates hidden `FilterBar`, `ColorLegend`,
`QTabBar`, status labels and progress widgets as “compatibility shims”
(`main_window.py:689-718`). Those shims are still the destination for active
logic:

- more than 40 operations call `statusBar().showMessage()` after the native
  status bar was hidden;
- structured progress writes `_progress_bar`/`_status_stage`, not the visible
  integrated bar;
- `IntegratedStatusBar.set_diff_position()` has no caller, leaving `0/0`;
- session capture/persistence reads hidden filter state;
- dynamic comparison documents are indexed through the hidden tab bar.

Retire the shims as state owners. Add explicit methods to the visible status
component (`show_message`, `set_progress`, `set_navigation_position`) and
route every caller through them. Temporary adapter methods on `MainWindow`
are acceptable during migration; temporary hidden widgets are not.

**Acceptance**:

1. A copy, delete, rename, sync, bookmark and drag/drop operation each produces
   visible feedback.
2. A synthetic progress event changes the visible percentage and stage.
3. Next/previous difference updates the visible counter.
4. No hidden widget owns user-visible state.
5. A source check or unit test rejects new `statusBar().showMessage()` calls.

### WI-5.8 — Repair session/document lifecycle and Merge reachability ✅
**Files**: `teczka/main_window.py`, `teczka/widgets/session_tab_bar.py`,
`teczka/widgets/sidebar.py`, `teczka/views/home_view.py`,
`teczka/models/settings.py`

Five related navigation defects were reproduced at runtime:

1. `_on_close_tab()` compares a visible session index against
   `_BASE_VIEW_TAB_COUNT` (6), so the first six session tabs cannot close and
   the deletion offset is wrong. The close-button image is also suppressed by
   the tab stylesheet, weakening the affordance even where closing is allowed.
2. Folder double-click creates a comparison widget in `_view_stack` but adds
   its label/data to the hidden `_view_switcher`; the opened document has no
   visible tab, natural return path or close action.
3. The sidebar exposes index 6 (“3-Way Merge”) while the initial stack has
   indices 0–5. `_switch_view(6)` returns without action, and the lazy merge
   toggle has no connected visible control.
4. Home emits `profile_selected`, but `MainWindow` never connects it. Home also
   looks for profiles in `comparison_settings["profiles"]`, while
   `ProfileManager` persists them in its own profiles file.
5. Home renders a Recent Sessions section, but no production code populates
   `recent_sessions`, so it remains an empty promise.

First restore a coherent lifecycle without redesigning the whole navigation
model: visible session tabs must close, dynamic comparisons must appear in a
visible tab surface, Merge must either be reachable or absent, and the two
Home collections must come from the same session/profile services that own the
data. WI-7.5 then consolidates the resulting model visually.

**Acceptance**: pytest-qt coverage for creating/switching/closing two sessions;
opening/reusing/closing Text, Hex, Image and Table comparisons; and entering/
leaving Merge. Selecting a profile opens the persisted pair and completing a
session adds a usable recent entry. No navigation destination or Home item may
be inert.

### WI-5.9 — Replace split filter/search state with one contract ✅
**Files**: `teczka/main_window.py`, `teczka/models/tree_model.py`,
`teczka/widgets/integrated_status_bar.py`; remove or repurpose
`teczka/widgets/filter_bar.py`

Introduce one typed `FolderFilterState` containing status visibility,
files-only, search text and high-level preset. The proxy model, View menu,
status pills, session persistence and configuration must all read/write that
object.

Correct the verified contradictions:

- the proxy defaults to `show_differences` while all four visible status pills
  appear enabled, so “Identical” says on while identical rows are hidden;
- View-menu toggles only update a hidden FilterBar whose signals are not
  connected;
- clicking a visible status pill passes `show_files_only=True`;
- session capture later reads stale hidden values;
- `Ctrl+F` focuses the hidden search field;
- Find Next/Previous always targets Folder view even when another view is
  active.

The default should be explicit: either show all and mark all controls on, or
show differences and mark Identical off. Never display a filter state that is
not the applied state.

**Acceptance**: a state-matrix test drives each input surface and asserts the
proxy, menu, footer and persisted session agree; `Ctrl+F` focuses the visible
contextual search; view changes cannot silently change files-only mode.

### WI-5.10 — Complete Settings/theme/CLI round-trip ✅
**Files**: `teczka/app.py`, `teczka/main_window.py`,
`teczka/dialogs/settings_dialog.py`, `teczka/resources/themes.py`,
`teczka/views/text_view.py`

There are two Settings handlers. The connected `_on_preferences()` stores
comparison and appearance values but ignores `get_config_updates()`, so Theme
and CLI Path are discarded. The more complete `_on_options()` is unconnected.
Consolidate them into one handler.

At application startup, apply the selected theme (or deliberately use the
system palette and remove the Light/Dark selector). If custom themes remain,
exercise both `load_light_theme()` and `load_dark_theme()` and refresh the
active widgets after a live change. Rebuild the CLI bridge when its path
changes and show validation feedback before closing.

The Appearance page also exposes Changed and Applied diff colours while
`TextView.apply_appearance()` consumes only Added and Removed. Either implement
the two roles throughout Text/Merge, or remove the controls until meaningful.

The same rule applies beyond Appearance. The Diff Options page exposes
whitespace, case, specialised comparison and regex controls, while the Files
page exposes encoding, EOL and binary-pattern controls; the connected
`get_settings()` path currently returns only ignore patterns, symlink/hash and
cache values. Wire each field through config and its comparison consumer, or
remove/disable it with honest “not yet available” copy. The CLI error message
must point to the actual Settings location rather than the nonexistent
“Tools > Options”.

**Acceptance**: restart round-trip tests for every Settings field; a visual
smoke test proves Light and Dark render differently; an invalid CLI path is
rejected actionably; every exposed appearance, Diff Options and Files value
has a reader and a behavioural test.

### WI-5.11 — Fix path-command ownership and contextual action state ✅
**Files**: `teczka/widgets/compact_path_bar.py`, `teczka/main_window.py`

`CompactPathBar._on_swap_clicked()` swaps locally and emits
`swap_requested`; `MainWindow._on_swap_sides()` receives the signal and swaps
again. The visible result is no change. Give mutation ownership to one layer:
recommended, the main/session state performs the swap and the path widget only
emits intent.

While touching action state, make the primary Compare action disabled until
both required paths are present and the CLI is available. Enable copy/sync/
apply/save/print actions only where the active document and selection support
them; presenting every action everywhere makes the menu feel unreliable.

**Acceptance**: one swap click reverses paths and session state exactly once;
the action-enablement matrix is tested for Home, empty Folder, populated
Folder, Text, Image, Hex, Table and Merge.

---

## Phase 6 — teczka structural refactor

**Status: not started.** Phase 5 deliberately left `MainWindow` large; what it
changed is that the boundaries the extraction needs now exist and are tested.
`_apply_filter_state()`, `_notify()`/`_set_progress()`/
`_set_navigation_position()`, `_switch_view()`/`_on_close_document()`,
`_close_session()` and `_update_action_states()` are the seams a
`NotificationController`, `NavigationController`, `SessionManager` and the
controllers below should be extracted along — and `tests/test_visible_shell.py`,
`tests/test_filter_state.py` and `tests/test_session_lifecycle.py` already
assert their observable behaviour, which is a meaningful part of WI-6.1.

The invasive tier. **Build the test net before moving code** — the current
suite covers `config`/`models`/`utils`/`widgets`, i.e. precisely the areas
*outside* the class being refactored, so it will not catch regressions here.

The full design review refines the extraction order. After WI-6.1, establish
the user-visible boundaries first: a `NotificationController` for message,
progress and error policy; a `NavigationController`/workspace model for active
documents; the typed `FolderFilterState` introduced in WI-5.9; then
`SessionManager`, `ComparisonController`, `FileOperationsController` and
`SyncController`. `MenuBuilder` remains last because it is mechanical. The
work items below may land in smaller commits, but must preserve this dependency
order so that refactoring does not recreate hidden state owners.

### WI-6.1 — Characterisation tests before any extraction (§2.8)
Write tests against current observable behaviour of the logic about to move:
sync planning, copy/delete paths, session capture/restore, profile save/load.
These are throwaway scaffolding in the sense that they assert today's
behaviour, including quirks — that is the point.

Include the visible-shell contracts established in WI-5.7–5.11: active
document, session count, path/filter state, action enablement, visible status
message and progress. These are the boundaries most likely to regress when
the compatibility widgets and `MainWindow` fields disappear.

### WI-6.2 — Extract `SyncController` / `FileOpsController` (§2.2)
`_plan_sync_actions`, `_sync_local_fallback`, `_copy_paths_local_fallback` and
`_sync_copy_path` implement file-operation semantics inside a widget class,
duplicating logic `rcompare_core` already owns and the CLI already exposes.

Move them out, and while moving, resolve the duplication: prefer delegating to
the CLI/core rather than reimplementing. First extract the visible
notification/progress and navigation boundaries described above; those are
the seams the controllers report through. The local fallback must never start
after a failed CLI sync without fresh confirmation: the engine, capability set
and risk can differ from the plan the user approved. Keep any fallback thin,
single-purpose and explicitly consented rather than a parallel implementation
that can drift.

### WI-6.3 — Extract `SessionManager` (§2.2)
Tab/session lifecycle: `SessionState`, `_capture_session_state`,
`_apply_session_state`, `_on_session_changed`, the `_sessions` list and
`_active_session_index`. Self-contained and highly testable once out.

### WI-6.4 — Extract `MenuBuilder` (§2.2)
~600 lines of action construction. Mechanical. Do it last of the three — it
is the lowest-risk and benefits from the shortcut test from WI-5.1 already
being in place.

### WI-6.5 — Resolve `AppState` (§2.3)
204 lines, 10 signals, **0 connections**; paths written at two sites and never
read while `MainWindow` uses its own `_left_path` in 29 places. Two parallel
state models, one inert.

Decide deliberately — both options are defensible, leaving it is not:
- **Finish it**: route path/result state through `AppState`, connect the
  signals, and let views observe it. This meaningfully shrinks `MainWindow`
  and composes with WI-6.2/6.3.
- **Delete it**: 204 lines gone and one less trap for the next contributor.

Recommendation: **finish it**, but only *after* WI-6.2/6.3 — those extractions
will show what state actually needs sharing, and doing it first would mean
guessing.

Make it the single source of truth completed by WI-5.7/WI-5.9 rather than
introducing another parallel layer. `SessionManager` should own durable
per-document/session state; `AppState` should expose only active, observable
runtime state. Views consume it but do not persist shadow copies.

**Acceptance**: no write-only state remains — every `AppState` setter has a
reader or a connected signal, enforced by a test.

### WI-6.6 — Coverage backfill on the extracted units
The real coverage win. Merge view first (youngest, most complex, least
verified), then the dialogs, then drag-and-drop. Previously WI-5.2.

Add design-regression coverage alongside functional coverage:

- screenshots for Home, Folder, Text, Hex, Image, Table, Merge and Settings at
  800×600 and 1440×900 in Light/Dark;
- shortcut collision detection;
- keyboard traversal of every primary action;
- accessible-name checks for icon-only controls;
- a “no inert visible controls” test for sidebar/menu destinations.

---

## Phase 7 — teczka presentation and KDE compliance

Presentation and accessibility tier. Palette and icon work can begin in
parallel, but navigation and contextual-chrome items depend on Phase 5 making
visible state authoritative. Absorbs the former Phase 6.

### WI-7.1 — Palette-derived theming (§2.5)
`resources/themes.py` is 1,531 lines with **390 hardcoded hex colours** and
**zero** `palette(...)` references; diff colours elsewhere are literals too
(`hex_view.py:41`). Plasma dark mode, accent colour and high-contrast
accessibility themes are all ignored.

The codebase is already inconsistent here — newer widgets (`breadcrumb_bar.py`,
`sidebar.py`) use `palette(...)` correctly. Extend that pattern to
`themes.py`. Diff colours need a semantic role map (added/removed/changed/
orphan) resolved against the active palette, not fixed hex.

WI-5.10 makes theme selection functional; this item makes the result coherent.
Use one semantic map across Folder, Text, Hex, Table and Merge. Today the same
concept changes colour by view (and Table maps both orphan directions to
yellow), while the hidden colour legend cannot explain any of it. Provide
light, dark and high-contrast variants plus a non-colour marker/icon for every
status.

This is the bulk of KDE **WS2 Theming (1/14)**.

### WI-7.2 — Colour the merge view's source panes (§2.9)
Only the merged output pane is tinted, so the user cannot see which regions
conflict in Left/Base/Right. The review calls this the single biggest
usability gap in the app's youngest feature. The diff data is already computed
(`_merge_lines`, `_opcodes_to_changes`) — this is a rendering gap, not an
algorithm one.

### WI-7.3 — Syntax highlighting (§1)
No `QSyntaxHighlighter` exists. Pygments is already a declared dependency via
PySide6's tooling. Add a highlighter to `widgets/diff_text_edit.py`, composed
*under* the existing intra-line diff tinting so both render together. Then
restore the `FEATURE_COMPARISON.md` row.

### WI-7.4 — Complete icon system and fallbacks (§2.6)
Main menu actions now use `_themed_icon()` in many places, but Home, Sidebar,
Settings and several secondary controls still call `QIcon.fromTheme()` with
no fallback. On a platform/session without a complete FreeDesktop theme the
rendered sidebar becomes a blank grey rail and Home cards reserve empty icon
space.

Route all icon lookup through `teczka/icons.py`: prefer the system theme, then
an embedded semantic fallback. Audit remaining menu actions, button-only
controls and application/window icons. Test with an intentionally empty icon
theme on Linux and on the Windows/macOS CI jobs from WI-0.4.

### WI-7.5 — Unify the navigation model (§2.9)
WI-5.8 restores correct lifecycle mechanics. This item completes the product
model: one visible tab represents one comparison document/session; its type is
Folder, Text, Hex, Image, Table or Merge. Home creates those documents and a
folder double-click opens/reuses a visible child document rather than changing
an invisible mode. The icon rail becomes a launcher/recent-documents surface
or is removed—do not keep a second navigation system.

Rename “New Session” and “Session 1” to match the chosen document model, make
close affordances consistent, persist open documents deliberately, and expose
the sidebar's existing expanded mode through a visible control if the rail
remains.

### WI-7.6 — Folder-view presentation parity (§2.9)
- Blank aligned gap for orphan rows instead of rendering the name on both
  sides in the same "different" tint.
- Per-pane file metadata strip (type, encoding, EOL, size, mtime) as BC has.
- Surface the existing filter/expand/collapse/swap/refresh actions in the
  toolbar — teczka *has* them, they are just undiscoverable.

Partly delivered: both panes now have structured Left/Right headers plus
independent, persisted column visibility/order/width with Name, Size,
Modified, Status, Extension, Type and Relative Path. Preserve this as the
reference component while adding the remaining parity items above.

### WI-7.7 — Route strings through the localizer, or remove it (§2.7)
`localizer.py` wraps `fluent.runtime` and `i18n/en/teczka.ftl` holds 152 lines
of messages, with **zero call sites**. Same failure mode as `AppState`.
Either adopt it across the UI or delete both. This is KDE **WS6 (1/12)**.

### WI-7.8 — Remaining KDE workstreams
Tracked in [KDE_COMPLIANCE.md](KDE_COMPLIANCE.md); ~35% against a ≥90% target.
After the items above, sequence the remainder by gap size:

1. **WS5 Desktop integration** — 0/17, the largest single hole.
2. **WS4 Dialogs** — 0/12.
3. **WS7 QA** — 0/13; overlaps WI-6.6, do them together.
4. **WS3 Shortcuts** — finish after WI-5.1 lands.

Update the score table in `KDE_COMPLIANCE.md` as each workstream lands — that
doc's numbers are the acceptance criteria.

### WI-7.9 — Remote/archive sources in the GUI
Depends on **WI-2.1**. Accept the URL syntax in teczka's path bar and file
dialogs, with credentials from the platform keyring. Resolution runs off the
GUI thread.

Partly delivered already: the path bar now has folder-picker buttons using the
portal/native chooser (`utils/path_picker.py`), so desktop-mounted network
locations (kio-fuse, GVfs) already work. What remains is rcompare's *own* VFS
schemes — `s3://`, `dav://` — which the desktop cannot mount.

### WI-7.10 — Sync preview against remote targets
Previously WI-5.3. Extend the sync-preview dialog to render the capability
warnings from WI-1.2 (e.g. "target does not support trash; deletes will be
permanent").

### WI-7.11 — Responsive Home and purposeful empty states
**Files**: `teczka/views/home_view.py`, all comparison views

The declared 800×600 minimum clips the Home cards: fixed 180×140 cards,
24-pixel vertical spacing and 120-pixel list minima exceed the content area
remaining after menu/session/path/status chrome. Replace the fixed 2×2 layout
with a responsive grid/flow inside a scroll area; validate 800×600, 125–200%
display scaling and long translated labels.

Home must represent every reachable document type (including Table and Merge)
and use the same terms as WI-7.5. Recent sessions/profiles need an explicit
single-click/Open affordance rather than unexplained double-click-only
activation.

Text, Hex, Image and Table currently open as large blank surfaces with small
“no file loaded” labels. Add a shared empty state with:

- a short explanation and supported-format guidance;
- primary Choose Left / Choose Right actions;
- drag-and-drop affordance;
- recent pair/profile shortcuts where relevant;
- loading, error and partial-pair variants.

**Acceptance**: no clipping or horizontal control overlap at the supported
minimum and scaling factors; every empty view tells the user what to do next.

### WI-7.12 — Accessibility baseline
**Files**: all visible teczka widgets/dialogs; add `tests/test_accessibility.py`

Establish a keyboard, screen-reader and contrast baseline:

1. Remove `NoFocus` from status filter pills and previous/next navigation;
   provide visible focus rings and logical Tab order.
2. Fix unchecked pill styling (`background-color` and `color` are both
   `palette(mid)` today).
3. Add accessible names/descriptions to icon-only sidebar, breadcrumb edit,
   browse, swap, column, fit and navigation controls. Home cards must expose
   their title as the button's accessible name, not only as child labels.
4. Never communicate Same/Different/Left-only/Right-only/Unchecked through
   colour alone. Add a status icon/text/shape that remains distinguishable in
   monochrome and common colour-vision deficiencies.
5. Verify normal text ≥4.5:1 and large text/control indicators ≥3:1 in Light,
   Dark and high-contrast/system palettes.
6. Respect system font and reduced-motion preferences; avoid animation where
   it is not informative.

**Acceptance**: complete keyboard operation without a mouse; automated
accessible-name/focus-order checks; documented manual screen-reader pass on
one Linux AT-SPI environment plus Windows or macOS.

### WI-7.13 — Contextual chrome and shared comparison components
**Files**: `teczka/main_window.py`, `teczka/views/*`, new reusable widgets

The folder breadcrumb row and folder-only footer filters sit outside the view
stack, so they remain visible on Home, Text, Hex, Image, Table and Merge where
they are irrelevant. Introduce view contributions for:

- command/path bar;
- primary and secondary actions;
- search/filter controls;
- status summary, progress and navigation.

Only Folder Compare shows folder paths and folder-status filters. Text exposes
file paths, edit/save and line-difference navigation; Image exposes fit/zoom/
tolerance/metadata; Table exposes sheet/key/header controls; Merge exposes
conflict navigation and resolution.

Build shared `ComparisonPaneHeader`, `ComparisonToolbar`,
`EmptyComparisonState` and responsive `MetricStrip` components. Use them to
replace the current mixture of bare labels, group boxes and per-view button
rows. The Image statistics strip must wrap/collapse instead of placing seven
metrics in one fixed horizontal row; the Merge conflict toolbar must expose
overflow at narrow widths rather than clipping.

### WI-7.14 — Action hierarchy, destructive safety and feedback language
Define one action hierarchy across menus, toolbars and dialogs:

- one primary action per state (`Compare`, `Run Dry Run`, `Execute Sync`,
  `Save Merged`);
- destructive actions carry a clear direction/target and confirmation;
- unavailable actions are disabled with an explanatory tooltip;
- completion messages state what changed, where, and whether undo is
  available;
- progress states distinguish queued, scanning, comparing, cancelling,
  cancelled, completed and failed.

Upgrade Sync Preview from a proportional-font text dump to a structured,
sortable operation table with direction, action, path, reason and risk.
Preserve dry-run/trash as safe defaults, show operation counts prominently,
and require a second confirmation when permanent deletion is selected.

Correct the present false safety boundary: the dialog says “Execute changes
on confirmation”, but its Execute button immediately starts the operation and
there is no later confirmation. Either make that button the clearly labelled
final confirmation (including source, target and destructive counts) or add
the promised confirmation step. A failed CLI execution must not silently fall
back to a local implementation under the original approval; show the failure
and require the user to approve a newly previewed fallback plan.

**Acceptance**: tests prove dry run never mutates; ordinary execution has
exactly one unambiguous final consent boundary; permanent deletion requires a
separate explicit confirmation naming the target and count; CLI failure cannot
trigger local mutation without a new preview and consent.

### WI-7.15 — Settings/dialog and product-language polish
Finish the secondary surfaces after the state and theme work:

- remove “Configure Toolbars…” while no configurable toolbar exists, or ship
  the actual feature;
- show “About KDE” only in a KDE environment;
- standardise `RCompare` capitalization and Folder/Text/Hex/Image/Table/Merge
  terminology;
- raise subtitle/helper-text contrast from `palette(mid)` where it fails;
- use consistent button boxes, default buttons, spacing and validation;
- ensure west-position Settings tabs remain readable under scaling and
  localisation, switching to a labelled category list if necessary;
- make online Help/Report Bug failure states actionable and retain an offline
  help entry point.

**Acceptance**: terminology inventory has no unintended `rcompare`/`RCompare`
or Session/Document inconsistency; no visible placeholder menu items; all
dialogs pass the responsive/accessibility checks from WI-7.11/WI-7.12.

---

## Phase 8 — Scale and net-new core

Opportunistic; none of it blocks parity.

| Item | Trigger to start |
|---|---|
| SQLite-backed index | When a real user tree exceeds ~100k files (current in-memory `HashMap` is fine below that) |
| Snapshot VFS | After Phase 2 stabilizes; it composes with the VFS layer |
| `.zst` compression | Any time; ~1 day, `.gz`/`.bz2`/`.xz` already work |
| ISO read, RAR write, GCS/Azure/Dropbox/OneDrive | Only on user request — all niche |
| Watch mode, semantic/AST diff, Git VFS | Deferred; low value vs. dedicated tools |
| `proptest` / fuzzing for parsers | Good first-contributor work; patch and CSV parsers first |

**Explicitly out of scope**: plugin system, REST/gRPC server, shell-extension
integrations. Unchanged from `roadmap.md`.

---

## Phase 9 — Beyond Compare configuration parity

Derived entirely from the 2026-07-26 configuration-surface study. Unlike
Phases 5–7, **this phase is not GUI-only**: over half the items need
`rcompare_core` and CLI support before teczka can expose anything, so each item
below states which side it lands on. Nothing here is a correctness defect —
these are capabilities teczka does not have.

Sequence by leverage: WI-9.1 first (it is the container the rest configure),
then WI-9.2/9.3 (the settings users hit first), then the engine-heavy items.

### WI-9.1 — Per-session settings dialog with a scope selector
**Side**: GUI. **Files**: new `teczka/dialogs/session_settings_dialog.py`,
`teczka/main_window.py`, `teczka/models/settings.py`

The structural gap. `SessionState` already holds per-tab `ComparisonSettings`
and `FolderFilterState`, and session switching already captures and reapplies
them — but the only way in is `Configure RCompare`, which writes the active
session *and* global config together. Add a session-scoped dialog with BC's
three-way scope control: **this view only** / **save into the session** /
**default for new sessions**.

This is a prerequisite for WI-9.2, WI-9.3 and WI-9.6 having anywhere sensible
to live; without it every new setting added below becomes another global.

**Acceptance**: changing a setting at "this view only" scope leaves a second
session and the persisted defaults untouched; promoting to default affects
newly created sessions and not existing ones; a round-trip test per scope.

### WI-9.2 — Comparison criteria parity
**Side**: core + CLI, then GUI. **Files**:
`rcompare_core/src/scanner.rs`, `rcompare_cli/src/main.rs`,
`teczka/models/settings.py`

Add, in rough order of user impact:

1. **Timestamp tolerance** (`--mtime-tolerance <seconds>`). The single most
   valuable item: FAT/exFAT and many network filesystems store coarser
   timestamps, so exact mtime comparison reports false differences today.
   BC defaults to 2 seconds.
2. **Ignore DST (1 hour)** and **ignore timezone differences** — the classic
   cross-platform archive-vs-local mismatch.
3. **Unix metadata comparison**: permissions, owner, group, as independent
   toggles with their own diff status.
4. **Content-compare mode**: CRC vs binary vs rules-based, plus "skip if quick
   tests indicate same". teczka has only a boolean `use_hash_verification`.
5. **Filename case comparison** and **align filenames differing only in
   Unicode normalisation form** (NFC vs NFD — the macOS/Linux trap).

**Acceptance**: fixture trees whose mtimes differ by 1 s, 1 h and a timezone
offset compare equal under the relevant flag and different without it; a
permissions-only difference is reported when enabled and ignored when not; NFC
and NFD spellings of the same filename align under the flag.

### WI-9.3 — Structured name filters and rule-based filters
**Side**: core + CLI, then GUI.

Replace the single `ignore_patterns` list with BC's four independent mask
lists — **include files / exclude files / include folders / exclude folders** —
and add reusable **filter presets**. Keep `--ignore` working as an alias for
exclude-files for one release.

Then add the Other Filters tier: rules on **size**, **date** and **attributes**
rather than name. `.gitignore` handling stays as-is — that remains a teczka
differentiator BC lacks.

**Acceptance**: an include-folders mask restricts traversal without excluding
matching files elsewhere; presets survive restart; existing `--ignore`
invocations behave unchanged.

### WI-9.4 — Workspaces
**Side**: GUI. **Files**: `teczka/models/settings.py`, `teczka/main_window.py`

A workspace is a named set of open sessions, loadable and saveable as a unit
(BC: `Session > Load Workspace` / `Save Workspace As`). teczka has sessions and
`SessionProfile` but nothing that groups them. Pairs naturally with the
`Startup` preferences in WI-9.9 ("load workspace on start", "save workspace on
exit").

Land after WI-7.5 settles the document/session model, or the workspace will
serialise a model that is about to change.

### WI-9.5 — File-format rules engine and "ignore unimportant differences"
**Side**: core, then CLI, then GUI. **Files**: new
`rcompare_core/src/grammar.rs`, `rcompare_core/src/text_diff.rs`

The largest single capability gap in the product, and the reason BC's text
comparison feels smarter than teczka's.

BC ships 24 file formats, each carrying a **grammar**: named elements
(Keyword, Identifier, Number, String, Comment, Operator, Environment Variable)
defined as regexes or delimited ranges, plus **line weights with priorities**.
The Importance tab then marks which grammar elements *matter*, which is what
makes "Ignore Unimportant Differences" work — a comment-only or
whitespace-only change is detected as unimportant and the file reports as
equal.

Scope this deliberately; it is a multi-week item:

1. A grammar model plus a rules file format, seeded with the languages already
   in `FEATURE_COMPARISON.md`'s syntax-highlighting scope (WI-7.3 shares the
   tokeniser — do these together, not twice).
2. An importance mask per format, and a diff pass that classifies each change
   as important/unimportant.
3. `--ignore-unimportant` on `scan` and `diff-file`; the View-menu toggle and
   the "Minor" indicator in teczka.
4. Per-session grammar overrides and unimportant-text rules.

**Acceptance**: two files differing only in comments compare equal under
`--ignore-unimportant` and different without it; the same for
whitespace-only and case-only changes per the importance mask; grammar
definitions round-trip through the rules file.

### WI-9.6 — Configurable text alignment, replacements and overrides
**Side**: core + CLI, then GUI. **Files**: `rcompare_core/src/text_diff.rs`

BC exposes four alignment algorithms — **Unaligned**, **Standard**, **Myers
O(ND)**, **Patience Diff** — plus **skew tolerance** (default 2000 lines) and
**closeness matching**. Patience Diff in particular produces markedly better
results on reordered blocks, which is a common complaint about naive LCS
output.

Add alongside: per-session **Replacements** (left↔right text substitutions
applied before comparison — teczka has `regex_rules`, which is the same idea
and may subsume it) and folder-level **Alignment overrides** (explicit
left-name↔right-name pairings, for renamed files).

**Acceptance**: a reordered-block fixture yields fewer reported changes under
Patience than Standard; skew tolerance bounds the search as documented; an
alignment override pairs two differently-named files.

### WI-9.7 — Table/CSV parsing controls
**Side**: core + CLI, then GUI. **Files**: `rcompare_core/src/csv_diff.rs`,
`teczka/views/table_view.py`

BC's Table Format dialog exposes delimiters (comma/semicolon/space/tab/other),
text qualifier (quote/apostrophe/none/other), fixed-width vs delimited, "treat
consecutive delimiters as one", "treat surrounding whitespace as part of
delimiter", **first line contains** (detect/header/data), and a Regional tab
for decimal separator, thousands separator, date order and date separator.

teczka assumes comma-delimited, quote-qualified, and got a header toggle and
key columns in WI-5.3. The regional settings matter for this project's own
Italian data: `1.234,56` and `DMY` dates are misparsed under the current
assumptions.

**Acceptance**: a semicolon-delimited Italian-locale CSV with `,` decimals
parses correctly; fixed-width input aligns by column; consecutive-delimiter
handling is covered both ways.

### WI-9.8 — Remote connection profiles and credential storage
**Side**: GUI, depends on **WI-2.1**. **Files**: new
`teczka/dialogs/connection_profiles_dialog.py`

BC's `Tools > Profiles` manages named remote connections (FTP/SFTP/SSH) with
Global/Server/Connection/Proxy/Listings/Transfer tabs, SSH key and SSL client
certificate paths, and per-profile ASCII-type masks.

WI-7.9 gives teczka's path bar URL syntax but no place to store credentials.
This is that place. **Credentials go in the platform keyring, never in
`pyside.json`** — and never in captured screenshots or logs.

### WI-9.9 — Global preferences parity
**Side**: GUI. **Files**: `teczka/dialogs/settings_dialog.py`,
`teczka/utils/config.py`

Eight of BC's 11 preference pages have no teczka counterpart. Add them in
value order, not the order BC lists them:

1. **File Operations** — 10 confirmation toggles (copy, move, read-only,
   system files, overwrite-newer, replace-during-move, content compare, delete,
   explicit side selection, merge) plus sync confirmation policy. teczka has
   the confirmation *dialogs* already (WI-7.14); this makes them configurable.
2. **Backups** — back up before copy/save, naming scheme, backup folder. Pairs
   with the existing undo-for-deletions support.
3. **Next Difference** — go to first difference on load, advance after copy,
   limit to current folder, wrap-around behaviour.
4. **Startup** — load workspace on start, save on exit (needs WI-9.4);
   file-manager context-menu integration is KDE **WS5** work, cross-reference
   rather than duplicate.
5. **Tabs** — open in new tab vs window, warn on closing multiple, hide tab bar
   when single.
6. **Text Editing** — auto-indent, backspace unindents, context-line count.
7. **Archive Types** — the mask table; low value until Phase 2 lands archive
   write.
8. **Open With** — user-defined external applications per file type.

Each toggle must have a consumer before it ships. The Phase 5 lesson stands:
a preference that does nothing is worse than an absent one.

### WI-9.10 — Command customisation beyond shortcuts
**Side**: GUI. **Files**: `teczka/dialogs/shortcuts_dialog.py`

BC's Commands page is a per-view table with **Menu**, **Toolbar** and
**Shortcut** columns — the user controls where each command appears, not just
its chord. teczka persists shortcuts (delivered in Phase 5) but has no menu or
toolbar placement control, and "Configure Toolbars…" was removed with the
toolbar itself.

Gate this on WI-7.5 deciding whether a toolbar exists at all. If it does not,
close this item as "won't do" rather than leaving it open indefinitely.

### WI-9.11 — Settings portability
**Side**: GUI. **Files**: `teczka/main_window.py`, `teczka/utils/config.py`

`Tools > Export Settings…` / `Import Settings…` / `Restore Factory Defaults…`.
Cheap to build on the existing JSON config and the standard way users migrate
between machines. Must exclude anything credential-shaped once WI-9.8 lands.

**Acceptance**: export/import round-trips every configured value; import of a
file from a newer schema version fails with a message naming both versions,
matching the WI-5.2 contract.

### WI-9.12 — Complete the View menu
**Side**: GUI. **Files**: `teczka/main_window.py`,
`teczka/widgets/color_legend.py`, `teczka/views/folder_view.py`

Four remaining View-menu gaps, two of them nearly free:

1. **Columns** submenu — BC offers 8 selectable fields (Ext, Revision, Size,
   CRC, Modified, Attributes, Owner, Group). teczka's `folder_columns` already
   persists widths and the folder view already supports column visibility and
   order; this is menu plumbing over existing capability.
2. **Legend** (`Ctrl+Alt+L`) — `color_legend.py` exists with no menu entry.
3. **Suppress Filters** — a temporary "show everything" override, distinct from
   clearing filters.
4. **Log panel** — BC keeps a per-session operation log; teczka's operation
   messages currently only pass through the status bar.

Items 1 and 2 are the cheapest parity wins in this phase; do them opportunistically
alongside any other folder-view work.

---

## Sequencing summary

```
RUST / ENGINE TRACK                    TECZKA / GUI TRACK

Phase 0 ──┬── WI-0.1 WebDAV fixes      Phase 5 ── correctness & contract
          ├── WI-0.2 gui dir cleanup     │  WI-5.1 shortcuts
          └── WI-0.4 CI matrix           │  WI-5.2 schema validation ──┐
                    │                    │  WI-5.3 CSV key alignment   │
                    ▼                    │  WI-5.4 worker cancel       │
Phase 1  ── SyncTarget / capabilities    │  WI-5.5 EXIF wiring         │
                    │                    │  WI-5.6 drag-drop           │
                    │                    │  WI-5.7 visible shell       │
                    │                    │  WI-5.8 tabs / Merge        │
                    │                    │  WI-5.9 filter state        │
                    │                    │  WI-5.10 Settings roundtrip │
                    │                    │  WI-5.11 swap/action state  │
       ┌────────────┼───────────┐        ▼                             │
       ▼            ▼           │   Phase 6 ── structural refactor     │
   Phase 2      Phase 3         │     WI-6.1 characterisation tests    │
  (backends)   (resume)         │     WI-6.2/3/4 extract controllers   │
       │                        │     WI-6.5 resolve AppState          │
       │                        │     WI-6.6 coverage backfill         │
       │                        │                                      │
       └────── WI-2.1 ──────────┼──▶ WI-7.9 (remote sources in GUI)    │
                                │                                      │
Phase 4 (CLI v2)                │   Phase 7 ── presentation/a11y/KDE  │
   WI-4.1 schema v2 ◄───────────┴───────── must come after ────────────┘

Phase 8 ── opportunistic

Phase 9 ── BC configuration parity (after Phase 5; spans both tracks)
   WI-9.1 session scope ──▶ WI-9.2 criteria, WI-9.3 filters, WI-9.6 alignment
   WI-9.5 grammar/rules ◄──── share one tokeniser ────▶ WI-7.3 highlighting
   WI-9.8 connection profiles ◄──── needs ──── WI-2.1
   WI-9.4 workspaces ◄──── after ──── WI-7.5 document model
```

The only hard cross-track dependency is **WI-5.2 → WI-4.1**.

**Single contributor:** WI-5.3 first (it fixes wrong output), then the
trust-critical GUI items 5.7 → 5.11, then 0 → 1 → 2 → 3, then the remainder
of 5 → 6 → 7, with 4 interleaved as appetite allows.

**Two contributors:** one takes the Rust track (0 → 1 → 2 → 3 → 4), the other
takes teczka (5 → 6 → 7). They meet at WI-2.1/WI-7.9 and at the
WI-5.2/WI-4.1 gate. This is the natural split — the tracks share almost no
files.

## Definition of done for each work item

1. Source change plus tests at the level the change lives (unit for core,
   integration for CLI, `pytest-qt` for teczka).
2. `cargo clippy` clean under the workspace lint config; no new `unsafe`.
3. Cross-platform: no new Linux-only assumptions (enforced by WI-0.4).
4. `roadmap.md` status flag updated — and only after checking against source,
   per that document's own standing rule.
5. `FEATURE_COMPARISON.md` row updated when a 🔌/❌ becomes ✅.
6. `CHANGELOG.md` `[Unreleased]` entry for anything user-visible.
7. GUI changes are exercised at 800×600 and 1440×900 in the relevant light,
   dark and high-contrast themes.
8. Keyboard navigation, focus order and accessible names are checked for every
   altered interactive control.
9. No visible control is inert and no hidden widget owns user-visible state.
