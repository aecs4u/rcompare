# Roadmap: remaining work for competitive parity

Last verified against source: 2026-11-08. Replaces `GAPS.md`, `ROADMAP.md`,
`ROADMAP_VFS.md`, and the forward-looking sections of the two dated CLI/GUI
milestone plans (all deleted this pass — see `CHANGELOG.md`). Competitor
baseline is [FEATURE_COMPARISON.md](../FEATURE_COMPARISON.md) (Beyond Compare,
WinMerge, Meld, KDiff3, P4Merge).

**Why this doc exists**: a source audit this pass found the previous
roadmap/gap docs wrong in both directions — some "done" items had regressed
or were never true, but more importantly several "planned"/"missing" items
were already built (archive write, RAR read, teczka tabs/drag-drop/3-way
merge/sync-preview). The single biggest pattern found: **real, tested
`rcompare_core` APIs that nothing in `rcompare_cli` or `teczka` calls.** The
first implementation pass has wired archive mutation, cloud endpoint
resolution, resumable local copies, and the WebDAV correctness fixes; the
remaining list now distinguishes partial frontend coverage from core gaps.

Status legend: ✅ Done · 🔌 Built but unwired · 🚧 Partial · ❌ Missing.

## 1. Highest-value near-term work (wiring, not new features)

These are the remaining highest-value integrations and quality gaps after the
first wiring pass. The underlying engines are generally already tested.

1. ✅ **Wire archive write (ZIP/TAR/7Z) into `rcompare_cli sync`/`copy`.**
   Writable archive VFSes now participate in the shared mutation endpoint,
   including recursive copy/delete and final flush. Teczka can invoke the
   same CLI paths; archive-specific viewers remain local-only.
2. 🚧 **Wire `ResumableCopy` into `sync`/`copy`.** `--checkpoint-dir` enables
   local file checkpoints; the engine validates the full source hash before
   resuming and saves progress on cancellation. `sync` stops between actions
   and during chunked transfers. Atomic sync manifests now support
   `sync-checkpoints`, `sync --resume-checkpoint ID`, and `sync-discard`; the
   CLI integration test covers listing, resume, and discard. Teczka now lists,
   resumes, and discards saved runs for the active roots, with GUI tests for
   these controls. A CLI test resumes a cancelled sync in a fresh process
   after SIGTERM. Live GUI Stop/Resume validation, copy-command cancellation,
   and automatic stale-checkpoint GC remain; directory recursion, archives,
   and remote streams still use the generic VFS transfer path.
3. 🚧 **Wire cloud VFS (S3/SFTP/WebDAV) into CLI path parsing and teczka's
   path bar** (e.g. `s3://bucket/path`, `sftp://host/path`). CLI scan,
   `diff-file`, `read`, `sync`, and `copy` now resolve these endpoints; the
   GUI forwards endpoint strings to CLI operations, stages selected remote
   folder rows through `read --out`, and opens them in existing viewers. The
   standalone picker accepts supported remote URLs and stages pairs through
   the CLI; live endpoint checks remain open.
4. ✅ **Fix the three WebDAV bugs**: Digest authentication is rejected rather
   than downgraded to Basic; PROPFIND uses namespace-aware XML parsing; and
   RFC3339/RFC1123 timestamps are parsed from server metadata. COPY/MOVE/PUT
   response status is also checked.
5. ✅ **Wire Union/Filtered VFS** (`rcompare_core::vfs::virtual_vfs`) into
   `scan` via repeatable `--overlay`, `--include`, and `--exclude` options.
   Include filters preserve directory traversal so nested matches remain
   discoverable. Impact: medium.
6. ✅ **Fix teczka's drag-and-drop >2-path truncation** (`main_window.py`
   now tells the user that only the first two paths are compared). Impact:
   low effort, real papercut.

7. ✅ **Make mutation failures observable.** `sync` and `copy` retain failed
   and missing items in their reports and now return a non-zero exit status
   after printing the report.
8. ✅ **Centralize source/target resolution and path validation.** URL sources
   no longer go through local existence prechecks; CLI defaults include cloud
   support; and mutation paths are validated at the endpoint boundary.
9. ✅ **Make archive replacement atomic.** Writable ZIP/TAR/7Z rebuild into a
   sibling temporary file, sync it, and replace the destination only after a
   successful rebuild.
10. 🚧 **Preserve transfer safety and streaming behavior.** Remote reads now
    stream S3, WebDAV, and SFTP responses into temporary files, keeping the
    returned reader bounded in memory and cleaning up on drop. Remote writers
    still buffer complete objects, and cancellation-aware transfer primitives
    remain open work.

11. ✅ **Add an opt-in mutation journal.** `sync` and `copy` accept
    `--transaction-log PATH` and append flushed JSONL lifecycle events for the
    run and each action, including planned, started, completed, and failed
    states. This provides an audit trail while resumable remote writes remain
    future work.

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
| Resumable sync/copy checkpoints, transaction log | 🚧 `--checkpoint-dir` covers local file transfers; sync manifests support discovery, option-checked restart, and discard; `--transaction-log` provides JSONL auditing. CLI restart after real cancellation and Teczka recovery controls are tested; live GUI Stop/Resume, copy-command cancellation, and automatic stale-checkpoint GC remain. | See §1.2 |
| Cancellation | 🚧 | Scan and sync cancellation are implemented; `sync` stops between actions and during chunked transfers, writes cancelled lifecycle events, and returns exit 130 with completed/remaining counts. Local file copies save checkpoints and verify source hashes. Copy-command cancellation remains. |

## 4. teczka (GUI)

| Item | Status | Impact |
|---|---|---|
| KDE/Plasma compliance | 🚧 ~35% (baseline was 5%, target ≥90%) | High — see [docs/KDE_COMPLIANCE.md](KDE_COMPLIANCE.md), single largest open GUI-quality gap |
| Automated GUI test coverage | 🚧 required CI job added; focused merge-view suite added | Medium — sync/export/profile dialogs and remote paths remain thin; merge still needs broader interaction coverage |
| Drag-and-drop >2-path handling | ✅ message clarifies first-two-path behavior | See §1.6 |
| Cloud/archive-write sources reachable from GUI | 🔌 depends on §1.1/§1.3 | High |

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
| teczka automated coverage | 🚧 — required CI job and focused merge-view suite added; sync/export/profile and remote paths remain thin | Medium |

Remaining implementation risks are tracked in §1.2, §1.3, §1.5, and §1.10
above. Archive and local mutation are now covered by CLI integration tests;
remote integration tests still require controlled service fixtures.

## Out of scope / intentionally deferred

Plugin/extension system, REST/gRPC API server, per-platform shell
integrations (Finder/Explorer/Nautilus extensions) — none started, all low
priority relative to the wiring work in §1. Not tracked further here unless
someone requests them.
