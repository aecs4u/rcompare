# Module: rcompare_common

Last verified against source: 2026-07-25.

Shared types, traits, and errors used by every other crate in the workspace.
Pure library crate, no I/O implementations of its own — those live in
`rcompare_core` ([docs/modules/rcompare_core.md](rcompare_core.md)). ~820 lines
across `src/{config,error,patch_types,types,vfs}.rs`.

## Contents

- **`vfs.rs`** — the `Vfs` trait every filesystem/archive/cloud backend
  implements: `metadata`, `read_dir`, `open_file`, `remove_file`, `copy_file`,
  `exists`. Write operations (`create_file`, `create_dir[_all]`, `rename`,
  `set_mtime`, `write_file`, `flush`) have default `Unsupported` implementations,
  overridden by backends that support them — see
  [docs/modules/rcompare_core.md](rcompare_core.md) for which ones actually do.
  `VfsCapabilities` lets callers introspect what a given backend supports
  (`read`/`write`/`delete`/`rename`/`create_dir`/`set_mtime`) without probing.
- **`types.rs`** — `FileEntry`, `FileMetadata`, `DiffStatus`/`DiffNode` (two-way
  compare), `ThreeWayDiffStatus`/`ThreeWayDiffNode`/`MergeResolution`/
  `MergeConflict`/`MergeResult`/`ConflictType`/`MergeSource` (three-way merge —
  the planning types produced by `rcompare_core`'s `MergeEngine`), `FileHash`/
  `CacheKey`/`Blake3Hash` (hash cache keys), `SessionProfile`/`AppConfig`
  (persisted GUI/CLI settings), `SessionId`.
- **`error.rs`** — `RCompareError` (top-level) and `VfsError` (backend-level,
  includes `Unsupported` used by the default trait methods above).
- **`patch_types.rs`** — `PatchSet`/`FilePatch`/`Hunk`/`PatchDifference`,
  `DiffFormat` (unified/context/normal/RCS/ed), `DiffGenerator` (CVS/Perforce/
  Subversion/plain), `HunkType`, `DifferenceType`. Consumed by the patch
  engine in `rcompare_core` and exposed to C via `rcompare_ffi`.
- **`config.rs`** — `LoadedConfig`, TOML config load/save.

## Design rule

Per [ARCHITECTURE.md](../../ARCHITECTURE.md) and `CLAUDE.md`: this crate must
stay UI- and I/O-agnostic. If you're adding a concrete filesystem/network
implementation, it belongs in `rcompare_core::vfs`, not here — this crate only
defines the trait/types those implementations conform to.
