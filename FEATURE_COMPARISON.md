# RCompare vs File Comparison Tools: Feature Comparison

Last updated: 2026-07-25

This document reflects current `rcompare` repository status (CLI + teczka PySide6/Qt6 GUI).
The earlier Slint-based `rcompare_gui` crate has been removed; teczka is now the only GUI.
Non-RCompare columns are best-effort snapshots and can vary by tool edition and release.

## Overview

| Tool | License | Language | Platforms | Active Development |
|------|---------|----------|-----------|-------------------|
| **RCompare** | Open Source (MIT/Apache-2.0) | Rust (+ PySide6 UI) | Linux, Windows, macOS | ✅ Yes |
| **Beyond Compare** | Commercial | C++ | Linux, Windows, macOS | ✅ Yes |
| **WinMerge** | Open Source (GPL) | C++ | Windows | ✅ Yes |
| **Meld** | Open Source (GPL) | Python/GTK | Linux, Windows, macOS | ✅ Yes |
| **KDiff3** | Open Source (GPL) | C++/Qt | Linux, Windows, macOS | ✅ Yes |
| **P4Merge** | Freeware | Proprietary | Linux, Windows, macOS | ✅ Yes |

### Key Differentiators

| Aspect | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 |
|--------|----------|----------------|----------|------|--------|
| Privacy posture | Privacy-first defaults (offline; optional Logfire if configured) | Unknown | Typically offline | Typically offline | Typically offline |
| Memory safety | ✅ Rust core | ⚠️ C++ | ⚠️ C++ | Python + native deps | ⚠️ C++ |
| Architecture | Modular (core + CLI + two GUIs) | Primarily monolithic app | Primarily monolithic app | Primarily monolithic app | Primarily monolithic app |
| Machine-readable CLI output | ✅ JSON | ⚠️ Limited | ⚠️ Limited | ⚠️ Limited | ⚠️ Limited |
| Native `.gitignore` handling | ✅ Yes | ⚠️ Partial/indirect | ❌ No | ❌ No | ❌ No |

---

## Core Comparison Features

### Folder Comparison

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 | P4Merge |
|---------|----------|----------------|----------|------|--------|---------|
| Side-by-side trees | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Recursive scanning | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Timestamp and size compare | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Basic |
| Hash verification | ✅ BLAKE3 | ✅ Multiple hashes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Orphan detection | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| Pattern filtering | ✅ Glob + `.gitignore` | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Limited | ❌ No |
| Session profiles | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Expand/collapse all | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |

### Text Comparison

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 | P4Merge |
|---------|----------|----------------|----------|------|--------|---------|
| Line-by-line diff | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Intra-line diff | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Syntax highlighting | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Limited | ⚠️ Limited |
| Ignore whitespace / case | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Limited |
| Regex rules | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Limited | ❌ No | ❌ No |
| Patience diff | ✅ Yes | ⚠️ Varies | ⚠️ Varies | ⚠️ Varies | ⚠️ Varies | ⚠️ Varies |
| 3-way merge workflow | ⏳ Planned for CLI/PySide UX (core merge engine exists) | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Conflict-resolution UI | ⏳ Planned with 3-way UX | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |

### Binary and Image Comparison

| Feature | RCompare | Beyond Compare | WinMerge | Meld | KDiff3 | P4Merge |
|---------|----------|----------------|----------|------|--------|---------|
| Hex view | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Hex diff highlighting | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Pixel-level image diff | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| EXIF metadata comparison | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| Image tolerance controls | ✅ Yes | ✅ Yes | ⚠️ Limited | ❌ No | ❌ No | ⚠️ Limited |
| Perceptual image hashing | ✅ Yes | ⚠️ Limited/indirect | ❌ No | ❌ No | ❌ No | ❌ No |

---

## Specialized Data Comparison

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| CSV structural comparison | ✅ Yes | ✅ Yes | Row/column-aware comparison |
| Excel comparison (`.xlsx`, `.xls`) | ✅ Yes | ⚠️ Varies by edition/rules | Sheet/cell-aware in RCompare |
| JSON structural comparison | ✅ Yes | ✅ Yes | Path-based structural diff |
| YAML structural comparison | ✅ Yes | ⚠️ Via text/rules | |
| Parquet comparison | ✅ Yes | ⚠️ Limited/indirect | DataFrame + schema checks in RCompare |
| MP3 tag comparison | ❌ No | ✅ Yes | BC niche strength |
| Registry comparison (Windows) | ❌ No | ✅ Yes | BC Windows-specific strength |

---

## Synchronization and File Operations

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Copy/move/delete | ✅ Yes | ✅ Yes | Includes trash-aware deletes |
| Bidirectional sync | ✅ Yes | ✅ Yes | CLI sync direction support |
| Dry-run sync planning | ✅ Yes | ✅ Yes | PySide also shows sync preview |
| Conflict policy controls | ✅ Yes (`newest/left/right/skip/error`) | ✅ Yes | |
| Selected-path copy | ✅ Yes (`copy --path/--paths-file`) | ✅ Yes | |
| Resume interrupted sync | ❌ No | ✅ Yes | Roadmap item for RCompare |

---

## Archive and VFS

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| ZIP/TAR/7Z read-write | ✅ Yes | ✅ Yes | |
| RAR read support | ✅ Yes | ✅ Yes | RCompare requires unrar backend |
| Compressed streams (`.gz/.bz2/.xz`) | ✅ Yes | ✅ Yes | |
| SFTP sources | ✅ Yes | ✅ Yes | |
| Cloud/WebDAV backends | ⚠️ Core support exists; UI parity still evolving | ✅ Yes | Check current release scope |
| Overlay/union virtual folders | ✅ Yes | ⚠️ Limited | |
| Snapshot VFS | ⏳ Planned | ❌ No | |

---

## UI and UX

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| Desktop GUIs | ✅ PySide6/Qt6 (teczka) | ✅ Yes | Slint GUI removed; teczka is the only frontend |
| Multi-tab sessions | ✅ Yes (PySide) | ✅ Yes | |
| Session profile manager | ✅ Yes | ✅ Yes | Save/load + auto-save on close |
| Persistent per-user options | ✅ Yes | ✅ Yes | Paths, filters, options, profiles |
| Folder-view modes | ✅ Compare structure / files-only / ignore structure | ✅ Yes | |
| Diff option presets | ✅ Yes (differences/orphans/newer modes) | ✅ Yes | |
| Rich context menu actions | ✅ Yes | ✅ Yes | Copy/move/delete/rename/touch/new folder/attributes/sync |
| File-type-aware double-click open | ✅ Yes | ✅ Yes | Opens compare tabs by file type |
| Drag and drop | ⏳ Planned | ✅ Yes | |

---

## Automation, Performance, and Privacy

| Feature | RCompare | Beyond Compare | Notes |
|---------|----------|----------------|-------|
| CLI command surface | ✅ `scan/sync/copy/diff-file/read/capabilities` | ✅ Yes | |
| JSON automation output | ✅ Yes | ⚠️ Limited | Strong CI/CD fit |
| Parallel scanning/hashing | ✅ Yes (rayon + BLAKE3) | ✅ Yes | |
| Persistent cache | ✅ Yes | ✅ Yes | |
| Open-source auditability | ✅ Yes | ❌ No | |
| Offline operation | ✅ Yes | ✅ Yes | |
| Telemetry behavior | Optional Logfire only when configured | Unknown | Defaults remain local/offline |

---

## Summary

### RCompare Strengths
1. Memory-safe Rust core with modular architecture.
2. Strong CLI automation story with JSON output.
3. Broad built-in specialized diff formats (CSV/Excel/JSON/YAML/Parquet/image EXIF).
4. Two GUI options, with PySide delivering advanced session/profile workflows.
5. Privacy-first defaults with explicit/optional telemetry configuration.

### Beyond Compare Strengths
1. Mature commercial product and support model.
2. Strong 3-way merge and conflict UI today.
3. Windows-specific specialized comparisons (for example registry/version tooling).
4. Broad ecosystem familiarity in enterprise teams.

### Practical Selection Guide

| Use Case | Better Fit |
|----------|------------|
| Open source + automation-heavy workflows | RCompare |
| Python/Rust-friendly, CI/CD-first pipelines | RCompare |
| Immediate production 3-way merge UX | Beyond Compare / KDiff3 |
| Windows-specific registry/version compare | Beyond Compare |
| Free Windows-only desktop compare | WinMerge |

---

## Roadmap Focus (RCompare)

### Recently Implemented
- Multi-tab PySide workspace.
- Per-user persistence for paths, filters, options, and profiles.
- Folder-view modes and diff option presets in PySide.
- Richer left/right context menus and file-type-aware double-click open.
- Sync preview dialog and improved session-profile handling.
- Text compare improvements (whitespace modes, ignore-case, regex rules).
- Image EXIF comparison and structured telemetry/logging integration.

### In Progress / Near-Term
- 3-way merge UX exposure in CLI/PySide.
- Drag-and-drop workflows in PySide.
- Progress/event streaming and schema evolution for CLI JSON.
- KDE-compliance hardening plan execution for PySide UX.

### Longer-Term
- Snapshot/reflink and larger-scale sync reliability features.
- Deeper VCS-backed virtual filesystem workflows.
- Full remote source parity in desktop UI for cloud/WebDAV backends.

---

## Sources and References

- [README.md](README.md)
- [docs/README.md](docs/README.md)
- [docs/RCOMPARE_CLI_FEATURE_ROADMAP.md](docs/RCOMPARE_CLI_FEATURE_ROADMAP.md)
- [docs/RCOMPARE_PYSIDE_KDE_COMPLIANCE_PLAN.md](docs/RCOMPARE_PYSIDE_KDE_COMPLIANCE_PLAN.md)
- [Beyond Compare](https://www.scootersoftware.com/)
- [WinMerge](https://winmerge.org/)
- [Meld](https://meldmerge.org/)
- [KDiff3](https://kdiff3.sourceforge.net/)
- [P4Merge](https://www.perforce.com/products/helix-core-apps/merge-diff-tool-p4merge)
