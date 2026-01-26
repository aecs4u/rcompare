# RCompare Gap List

This list tracks open gaps against ARCHITECTURE.md and FEATURE_COMPARISON.md.
Columns: Priority (P0 highest), Status (Open/In Progress/Done), Owner (optional).

| Priority | Gap | Impact | Status | Evidence | Notes | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | Hash verification in comparison flow | Incorrect "Same"/"Unchecked" results for same-size files | Done | `rcompare_core/src/comparison.rs`, `rcompare_cli/src/main.rs` | Wired `--verify-hashes` to core comparison | |
| P0 | VFS not used by scanner/comparison | Archives cannot be compared as folders | Done | `rcompare_core/src/scanner.rs`, `rcompare_cli/src/main.rs` | VFS scan + archive detection added | |
| P0 | Text diff UI missing | Core text diff not exposed to users | Done | `rcompare_core/src/text_diff.rs`, `rcompare_gui/ui/main.slint` | Text diff view wired into GUI | |
| P0 | GUI blocks on comparisons | UI freezes on large scans | Done | `rcompare_gui/src/main.rs` | Comparison work now runs off the UI thread | |
| P1 | Partial hash pre-check missing | Slower comparisons on large files | Done | `rcompare_core/src/comparison.rs` | Implemented 16KB partial hashing | |
| P1 | Virtual tree expand/collapse missing | Folder comparison lacks hierarchy | Open | `rcompare_gui/ui/main.slint` | Flatten tree model + expand/collapse | |
| P1 | Synced scrolling + gutter map missing | Usability gap vs spec | Open | `rcompare_gui/ui/main.slint` | Bind list view scroll and render diff map | |
| P1 | 3-way merge support missing | Required text merge feature | Open | no implementation | Add core merge + GUI controls | |
| P1 | JSON output missing in CLI | Automation gap | Done | `rcompare_cli/src/main.rs` | Added JSON report option | |
| P1 | Archive support incomplete (no 7Z) | Spec mismatch | Done | `rcompare_core/src/vfs/archive.rs` | 7Z read-only VFS added | |
| P1 | Image compare missing | Feature parity gap | Open | no implementation | Implement compare modes + UI | |
| P1 | Hex view UI missing | Binary compare not visible | Open | `rcompare_core/src/binary_diff.rs` | Add GUI/CLI rendering | |
| P2 | Config persistence (TOML) missing | Settings not saved | Open | no persistence code | Add load/save config in common | |
| P2 | Portable mode missing | Spec mismatch | Open | no lookup logic | Check config near binary | |
| P2 | .gitignore only for left root | Inconsistent filtering | Open | `rcompare_core/src/scanner.rs` | Load from both roots and respect hierarchy | |
| P2 | Glob matching is simplistic | Filtering not accurate | Open | `rcompare_core/src/scanner.rs` | Use globset or glob crate | |
| P2 | Cache format JSON option missing | Spec mismatch | Open | `rcompare_core/src/hash_cache.rs` | Optional JSON cache | |
| P2 | Parallel hashing missing | Performance gap | Open | no parallel hash | Use rayon for hashing queue | |
| P2 | Post-copy checksum verification missing | Data integrity gap | Open | `rcompare_core/src/file_operations.rs` | Verify after copy when enabled | |
| P2 | Resume interrupted copies missing | Reliability gap | Open | no implementation | Add resumable copy strategy | |
| P2 | UI tabs/multi-session missing | Usability gap | Open | `rcompare_gui/ui/main.slint` | Add tabs for sessions | |
| P2 | Keyboard shortcuts/context menus missing | UX gap | Open | `rcompare_gui/ui/main.slint` | Add shortcut bindings and menus | |
| P3 | Advanced compare features (moved lines/manual alignment/structured compare) | Power-user diff workflows | Open | `FEATURE_COMPARISON.md` | Survey-driven optional features | |
| P3 | Patch workflow + rich report exports | Automation/reporting parity | Open | `FEATURE_COMPARISON.md` | Patch create/apply/preview + HTML/XML/CSV | |
| P3 | Layout toggle + scripting/macros | Usability and automation | Open | `FEATURE_COMPARISON.md` | Horizontal/vertical + repeatable sessions | |
| P3 | Unicode/case/time normalization options | Comparison correctness | Open | `FEATURE_COMPARISON.md` | Unicode, casing, CRC, DST/timezone controls | |
