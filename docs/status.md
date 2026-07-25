# Project status

Last verified against source: 2026-07-25. Replaces `DEVELOPMENT_STATUS.md` and
`COMPLIANCE_MATRIX.md` (both deleted this pass — they had drifted from source;
see `CHANGELOG.md`). For what's left to build, see
[docs/roadmap.md](roadmap.md). For per-crate detail, see [docs/modules/](modules/).

## Workspace

| Crate | Role | Test count (`#[test]`, grep count not a full run) |
|---|---|---|
| `rcompare_common` | Shared types/traits, no I/O | ~4 |
| `rcompare_core` | Engine: comparison, VFS, merge, patch | ~301 |
| `rcompare_cli` | CLI (`scan`/`sync`/`copy`/`diff-file`/`read`/`capabilities`) | ~62 |
| `rcompare_ffi` | C FFI over the patch engine | ~37 |
| `teczka/` (Python) | PySide6/Qt6 GUI, shells out to `rcompare_cli` | 31 `pytest` functions across 4 files |

## What's solid

- Core comparison (hash/size/timestamp, parallel hashing, streaming large
  files), text/binary/CSV/Excel/JSON/YAML/Parquet/image diffing, the patch
  system (unified/context/normal/RCS/ed), and local-filesystem VFS are mature
  and well-tested. See [docs/modules/rcompare_core.md](modules/rcompare_core.md).
- Archive read (ZIP/TAR/7Z/RAR) and write (ZIP/TAR/7Z) both work at the core
  API level; RAR is read-only.
- Cloud VFS backends (S3, SFTP, WebDAV) are real, non-trivial implementations
  (500-600 lines each) — WebDAV has three known bugs (fake digest auth, naive
  PROPFIND parsing, mtime always reported as `now()`).
- teczka has a genuinely full-featured session model: multi-tab, per-tab state
  capture/restore, profile save/load with auto-save-on-close, a sync-preview
  dialog, a working three-way merge view, synced scrolling with a gutter map,
  a hex viewer, and drag-and-drop.

## What's not wired up (built, but unreachable from CLI/GUI)

The single biggest gap pattern in the project right now, not a missing-feature
problem: archive write, cloud VFS, Union/Filtered VFS, and the resumable-copy
checkpoint engine all exist and are tested in `rcompare_core`, but nothing in
`rcompare_cli` or `teczka` calls them. See [docs/roadmap.md §1](roadmap.md#1-highest-value-near-term-work-wiring-not-new-features)
for the prioritized list — this is the fastest path to closing remaining
competitive gaps.

## What's genuinely missing

SQLite index for very large trees, watch mode, semantic/AST diff, connection
pooling/retry for SSH/cloud, snapshot VFS, ISO support, `.zst` compression,
GCS/Azure/Dropbox/OneDrive backends, HTML/JUnit/Markdown report export,
unified JSON schema v2, `--progress-json`/`--ndjson` streaming, property-based/
fuzz testing. Full list with impact ratings in [docs/roadmap.md](roadmap.md).

## Known weak spots

- CI (`ci.yml`) runs the core/CLI test matrix on Linux only; Windows/macOS are
  only exercised at release time (`release.yml`).
- teczka's automated test coverage (31 pytest functions) is thin relative to
  its actual surface area — the merge view, sync/export/profile dialogs, and
  drag-and-drop have no automated tests.
- KDE/Plasma UX compliance is at roughly 35% (baseline was 5%, target ≥90%) —
  see [docs/KDE_COMPLIANCE.md](KDE_COMPLIANCE.md).
- `COMPLIANCE_MATRIX.md`, the doc this file replaces, was itself already stale
  before this pass (referenced pre-refactor file paths). If you need a formal
  requirements-traceability matrix again, it needs to be rebuilt from source,
  not resurrected from git history.
