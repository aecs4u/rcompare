# Development Plan

Created: 2026-07-25. Source-verified against the tree at commit `c17ea5d`.

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

---

## Phase overview

| Phase | Theme | Gates | Est. |
|---|---|---|---|
| 0 | Preconditions & correctness debt | — | 3–5 d |
| 1 | VFS-aware mutation path (the unlock) | P0 | 8–13 d |
| 2 | Backend wiring on top of Phase 1 | P1 | 7–11 d |
| 3 | Resumable sync/copy | P1 | 4–6 d |
| 4 | CLI automation surface (v2) | P1 (loosely) | 8–12 d |
| 5 | teczka: bugs, remote reach, tests | P2 | 10–15 d |
| 6 | teczka: KDE compliance to ≥90% | P0 | 12–18 d |
| 7 | Scale & net-new core | P2 | opportunistic |

Phases 4 and 6 are independent of 1–3 and can run in parallel if there's more
than one contributor. Phases 2, 3 and 5 are strictly downstream of Phase 1.

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

### WI-0.3 — Fix teczka's drag-and-drop truncation
**File**: [teczka/teczka/main_window.py:3237](../teczka/teczka/main_window.py#L3237)

`dropEvent` collects all dropped URLs then keeps the first two with no
feedback. Fix: when >2 paths are dropped, use the first two **and** say so in
the status bar. Cheap, and it's a user-visible papercut currently documented as
a defect in `FEATURE_COMPARISON.md`.

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

## Phase 5 — teczka: bugs, remote reach, tests

Depends on Phase 2 for remote sources; the test work does not.

### WI-5.1 — Remote/archive sources in the path bar
Accept the WI-2.1 URL syntax in teczka's path bar and file dialogs, with a
credential prompt backed by the platform keyring. Run resolution off the GUI
thread — the codebase already established that pattern in recent commits
(`comparison_worker.py`, background CSV/Excel parsing).

### WI-5.2 — GUI test coverage
Current state: 4 files, 271 lines total. Untested: merge view, sync/export/
profile dialogs, drag-and-drop. Target the merge view first — it's the
youngest, most complex, and least-verified surface in the app, and
FEATURE_COMPARISON.md already flags its conflict-resolution UI as
"young/undertested".

### WI-5.3 — Sync preview against remote targets
Extend the existing sync-preview dialog to render capability warnings from
WI-1.2 (e.g. "target does not support trash; deletes will be permanent").

---

## Phase 6 — KDE compliance to ≥90%

Tracked in detail in [KDE_COMPLIANCE.md](KDE_COMPLIANCE.md); current ~35%
against a ≥90% target. Sequence by remaining gap size:

1. **WS5 Desktop integration** — 0/17, the largest single hole.
2. **WS4 Dialogs** — 0/12.
3. **WS7 QA** — 0/13; overlaps WI-5.2, do them together.
4. **WS2 Theming** — 1/14; completes the partial color work already started.
5. **WS6 A11y/i18n** — 1/12.
6. **WS1/WS3** — already improved to 86%/75% on menus and shortcuts; finish the
   remainder last.

Update the score table in `KDE_COMPLIANCE.md` as each workstream lands — that
doc's numbers are the acceptance criteria for this phase.

---

## Phase 7 — Scale and net-new core

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

## Sequencing summary

```
Phase 0 ──┬── WI-0.1 WebDAV fixes ──────────────┐
          ├── WI-0.2 gui dir cleanup            │
          ├── WI-0.3 teczka DnD                 │
          └── WI-0.4 CI matrix ─────┐           │
                                    ▼           │
Phase 1  ── SyncTarget / capabilities / tests   │
                   │                            │
       ┌───────────┼────────────┐               │
       ▼           ▼            ▼               ▼
   Phase 2     Phase 3      Phase 5 ◄──── (WebDAV gate)
  (backends)  (resume)      (teczka)

Phase 4 (CLI v2) ── parallel, independent
Phase 6 (KDE)    ── parallel, independent
Phase 7          ── opportunistic
```

Single contributor: 0 → 1 → 2 → 3 → 4 → 5 → 6. Two or more: one takes 0→1→2→3,
the other takes 6 then 4, converging on 5.

## Definition of done for each work item

1. Source change plus tests at the level the change lives (unit for core,
   integration for CLI, `pytest-qt` for teczka).
2. `cargo clippy` clean under the workspace lint config; no new `unsafe`.
3. Cross-platform: no new Linux-only assumptions (enforced by WI-0.4).
4. `roadmap.md` status flag updated — and only after checking against source,
   per that document's own standing rule.
5. `FEATURE_COMPARISON.md` row updated when a 🔌/❌ becomes ✅.
6. `CHANGELOG.md` `[Unreleased]` entry for anything user-visible.
