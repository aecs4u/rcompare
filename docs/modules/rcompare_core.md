# Module: rcompare_core

Last verified against source: 2026-07-25 (comparison.rs, merge_engine.rs,
patch_engine.rs, vfs/{archive,s3,sftp,webdav,virtual_vfs}.rs read directly;
status below reflects actual code, not prior docs — several older docs in this
repo had this module's status wrong in both directions, see
[docs/roadmap.md](../roadmap.md) intro).

The engine. UI-agnostic business logic — no GUI or CLI dependencies. ~17,500
lines across `src/`. Cargo features (all on by default): `cloud` (S3/SFTP/
WebDAV), `archives` (ZIP/TAR/7Z/RAR + compressed streams), `specialized`
(CSV/Excel/JSON/Parquet/image diffing, itself split into per-format sub-features).

## Comparison engine (`comparison.rs`, 1465 lines)

`ComparisonEngine`: size/timestamp/BLAKE3-hash comparison, with:
- **Parallel hashing** — `hash_files_parallel()`, rayon-based, `with_hash_concurrency()`
  to bound the pool. Done.
- **Streaming large-file comparison** — `with_streaming_threshold()` (default
  100MB), chunk-by-chunk with early exit on mismatch. Done.
- **Three-way comparison** — `compare_three_way[_with_vfs]()` produces
  `ThreeWayDiffNode`s (tree-level, see Merge engine below). Done.
- Persistent BLAKE3 cache via `hash_cache.rs` (392 lines).

## Merge engine (`merge_engine.rs`, 681 lines)

`MergeEngine::merge(base, left, right)` → `MergeResult`s. This is a **tree-level
planner**, not a content/line-level differ: `is_modified()`/`is_same_content()`
compare only size+mtime, not bytes. It classifies conflicts (`BothModified`,
`ModifyDelete`, `BothAdded`, `TypeConflict`) and produces resolutions
(`UseLeft`/`UseRight`/`AutoMerged`/`ManualRequired`/`UseBase`). Line-level 3-way
text diffing for the actual merge UI happens independently in teczka
(`views/merge_view.py`, via Python's `difflib`) — see
[docs/modules/teczka.md](teczka.md). Done at the tree-planning level.

## VFS backends (`vfs/`)

All implement the `Vfs` trait from `rcompare_common` ([docs/modules/rcompare_common.md](rcompare_common.md)).

| Backend | Read | Write | Status | Wired into CLI/GUI? |
|---|---|---|---|---|
| Local (`vfs/local.rs`) | ✅ | ✅ | Done | Yes |
| ZIP (`vfs/archive.rs`, `WritableZipVfs`) | ✅ | ✅ | Done | **No — core API only** |
| TAR/TAR.GZ/TGZ (`WritableTarVfs`) | ✅ | ✅ | Done | **No — core API only** |
| 7Z (`Writable7zVfs`) | ✅ | ✅ | Done | **No — core API only** |
| RAR (`unrar` crate) | ✅ | ❌ | Read-only; no password-protected archive support | Yes, read path only |
| Compressed streams (`.gz/.bz2/.xz`) | ✅ | ✅ | Done | No |
| Compressed streams (`.zst`) | — | — | **Missing** | — |
| ISO images | — | — | **Missing** | — |
| Union/overlay VFS (`vfs/virtual_vfs.rs`, `UnionVfs`) | ✅ | — | Real, unit-tested (layered lookup, override semantics) | **No — core API only** |
| Filtered VFS (`virtual_vfs.rs`, `FilteredVfs`) | ✅ | — | Real, glob include/exclude wrapper | **No — core API only** |
| Snapshot VFS | — | — | **Missing** | — |
| S3 (`vfs/s3.rs`, 509 lines) | ✅ | ✅ | Full CRUD, paginated listing, default/access-key/anonymous auth; `set_mtime` correctly reported unsupported (S3 limitation) | **No — core API only** |
| SFTP (`vfs/sftp.rs`, 345 lines) | ✅ | ✅ | password/key-file/ssh-agent auth | **No — core API only** |
| WebDAV (`vfs/webdav.rs`, 587 lines) | ✅ | ✅ | See bugs below | **No — core API only** |
| Git repository VFS | — | — | **Missing** | — |

**WebDAV known bugs** (real, not just gaps — see [docs/roadmap.md](../roadmap.md)):
1. "Digest" auth silently falls back to Basic (`webdav.rs:117-121,545-548`, the
   fallback is an explicit comment, not an oversight-shaped bug).
2. PROPFIND response parsing is substring search, not a real XML parser
   (`webdav.rs:132-133`, comment: "simplified implementation for demonstration").
3. `parse_date()` always returns `SystemTime::now()` — WebDAV file mtimes are
   **not actually read** from the server (`webdav.rs:165-170`).

**No connection pooling or retry/backoff** for any cloud/SSH backend (grep-confirmed
absent from `s3.rs`/`sftp.rs`/`webdav.rs`).

## Other engines

- **Patch system** (`patch_engine.rs` + `patch_parser/{unified,context,normal,rcs,ed}.rs`
  + `patch_serializer.rs`): parse unified/context/normal/RCS/ed diff formats,
  auto-detect generator (CVS/Perforce/Subversion), `apply_difference`/
  `unapply_difference`/`apply_all`/`unapply_all`/`blend_file`/
  `reconstruct_destination`. Exposed to C via `rcompare_ffi` — see
  [docs/modules/rcompare_ffi.md](rcompare_ffi.md). Done, mature.
- **Text diff** (`text_diff.rs`): line + intra-line diff via the `similar` crate
  (Myers/Patience), whitespace modes, case-insensitive.
- **Binary diff** (`binary_diff.rs`): hex-level comparison.
- **Specialized diffs**: `csv_diff.rs`, `excel_diff.rs`, `json_diff.rs`
  (also handles YAML), `parquet_diff.rs`, `image_diff.rs` (pixel diff + EXIF +
  tolerance + perceptual hashing).
- **File operations** (`file_operations.rs`): copy/move/delete with post-copy
  BLAKE3 verification and retry.
- **Resumable copy** (`resumable_copy.rs`, 554 lines): `ResumableCopy` engine
  with JSON checkpoints, 4MB chunks, 100MB checkpoint interval, partial-hash
  resume validation. Fully built and tested — **but has zero callers** outside
  its own tests; `rcompare_cli`'s `sync`/`copy` commands don't use it yet. See
  [docs/roadmap.md](../roadmap.md) — this is one of the highest-value/lowest-effort
  wiring gaps in the project.
- **Scanner** (`scanner.rs`, 745 lines): parallel traversal via `jwalk`, nested
  `.gitignore` loading.

## Confirmed missing (no trace in source)

SQLite-backed index for very large trees, watch mode (continuous monitoring —
no `notify::` dependency anywhere), semantic/AST-based diff.
