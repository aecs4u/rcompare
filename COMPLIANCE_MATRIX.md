# RCompare Compliance Matrix

Status legend: Implemented, Partial, Missing, Not verified

## ARCHITECTURE.md Requirements

| Area | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| Workspace | Cargo workspace with common/core/cli/gui | Implemented | `Cargo.toml` |
| Modularity | Shared types/errors/traits in common | Implemented | `rcompare_common/src/types.rs`, `rcompare_common/src/error.rs`, `rcompare_common/src/vfs.rs` |
| Modularity | Core library has no GUI deps | Implemented | `rcompare_core/Cargo.toml` |
| Modularity | CLI wraps core | Implemented | `rcompare_cli/src/main.rs` |
| Modularity | GUI frontend in Slint | Implemented (basic) | `rcompare_gui/ui/main.slint` |
| Safety | Unsafe only in sys module | Implemented (no unsafe found) | repo search |
| Privacy | Offline, no telemetry | Not verified | no network code found |
| Concurrency | Parallel traversal | Implemented | `rcompare_core/src/scanner.rs` |
| Concurrency | Parallel heavy tasks (hash/diff) | Partial | `rcompare_core/src/file_operations.rs` (rayon), hashes not parallel |
| VFS | Vfs trait in common | Implemented | `rcompare_common/src/vfs.rs` |
| VFS | LocalVfs implementation | Implemented | `rcompare_core/src/vfs/local.rs` |
| VFS | Archive VFS (ZIP/TAR/7Z) | Partial | `rcompare_core/src/vfs/archive.rs` (ZIP/TAR only) |
| VFS | VFS used by scanner/comparison | Implemented | `rcompare_core/src/scanner.rs`, `rcompare_core/src/comparison.rs` |
| Scanning | Alignment into DiffNode tree | Implemented (basic) | `rcompare_core/src/comparison.rs` |
| Scanning | Memory optimization for large trees | Missing | no interning/Arc strings |
| Hashing | BLAKE3 hashing | Implemented | `rcompare_core/src/comparison.rs` |
| Hashing | Partial hash pre-check | Implemented | `rcompare_core/src/comparison.rs` |
| Hashing | Persistent cache | Implemented (bin only) | `rcompare_core/src/hash_cache.rs` |
| Hashing | Hash verification in comparison flow | Implemented | `rcompare_core/src/comparison.rs`, `rcompare_cli/src/main.rs`, `rcompare_gui/src/main.rs` |
| Text diff | Myers/Patience diff | Implemented (core only) | `rcompare_core/src/text_diff.rs` |
| Text diff | Intra-line diff | Implemented (core only) | `rcompare_core/src/text_diff.rs` |
| Text diff | Syntax highlight rendering | Partial | core segments only |
| GUI | Virtual tree (flatten/expand/collapse) | Missing | `rcompare_gui/ui/main.slint` |
| GUI | Synced scrolling + gutter map | Missing | `rcompare_gui/ui/main.slint` |
| GUI | Text diff view + merge UI | Partial | text diff view implemented; merge UI missing |
| Config | TOML config load/save | Missing | no persistence code |
| Config | Portable mode | Missing | no lookup near binary |
| Error handling | thiserror/anyhow strategy | Implemented | `rcompare_common/src/error.rs` |
| Logging | tracing in CLI/GUI | Implemented | `rcompare_cli/src/main.rs`, `rcompare_gui/src/main.rs` |

## FEATURE_COMPARISON.md Requirements

| Category | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| Folder | Recursive scanning | Implemented | `rcompare_core/src/scanner.rs` |
| Folder | Orphan detection | Implemented | `rcompare_core/src/comparison.rs` |
| Folder | Hash verification | Implemented | `rcompare_core/src/comparison.rs`, `rcompare_cli/src/main.rs` |
| Folder | Glob filtering | Partial | simple matcher `rcompare_core/src/scanner.rs` |
| Folder | .gitignore support | Partial | left side only |
| Text | Line diff | Implemented | `rcompare_gui/src/main.rs`, `rcompare_gui/ui/main.slint` |
| Text | Syntax highlighting | Implemented | `rcompare_core/src/text_diff.rs`, `rcompare_gui/src/main.rs` |
| Text | 3-way merge | Missing | no core/UI |
| Binary | Hex viewer | Partial | core only `rcompare_core/src/binary_diff.rs` |
| Binary | Lazy loading | Partial | `read_chunk_at_offset` only |
| Image | Compare modes | Missing | no implementation |
| Sync | Copy/move/delete | Partial | core only `rcompare_core/src/file_operations.rs` |
| Sync | Dry run | Partial | core only |
| Sync | Touch timestamps | Partial | core only |
| Archive | ZIP/TAR/7Z | Implemented | ZIP/TAR/TAR.GZ/7Z |
| Archive | Transparent compare | Implemented | supported for .zip/.tar/.tar.gz/.7z via VFS |
| Automation | CLI present | Implemented | `rcompare_cli/src/main.rs` |
| Automation | JSON output | Implemented | `rcompare_cli/src/main.rs` |
| UI | Tabs/multi-session | Missing | no UI |
| UI | Keyboard shortcuts | Missing | no UI |
| Performance | Parallel hashing | Missing | no parallel hashing |
| Privacy | Zero telemetry | Not verified | no network code found |
