# RCompare Roadmap

Status legend: Not started, In progress, Done

## Milestone 1: Folder Compare UX Core (In progress)
- Virtual tree model (flattened rows with depth + expand/collapse) - Done
- Tree row selection model + keyboard navigation - Not started
- Synced scrolling between left/right panes - Not started
- Gutter diff overview map - Not started
- Folder list click opens text diff - Done

## Milestone 2: Text Compare + Merge (Not started)
- 3-way merge core logic - Not started
- Merge UI controls (Take Left/Right/Both/None) - Not started
- Editable text view with debounced diff - Not started
- Ignore whitespace/case options - Not started

## Milestone 3: File Operations + Sync (Not started)
- Expose copy/move/delete/touch in CLI - Not started
- Expose copy/move/delete/touch in GUI with confirmations - Not started
- Dry-run preview and progress reporting - Not started
- Post-copy checksum verification option - Not started

## Milestone 4: Archive + VFS Maturity (In progress)
- VFS-backed comparison for archives (.zip/.tar/.tar.gz/.7z) - Done
- Archive selection in GUI - Done
- Streaming 7z support (avoid full extraction) - Not started
- Archive-in-archive traversal (if in scope) - Not started

## Milestone 5: Config + Portability (In progress)
- TOML config load/save (XDG/AppData/Library) - Done
- Portable mode (config next to binary) - Done
- Settings dialog in GUI - Not started

## Milestone 6: Quality & Performance (Not started)
- CLI integration tests for JSON/hashes (baseline) - Done
- Benchmark large folder scans (1M+ files) - Not started
- Performance profiling + caching improvements - Not started

## Milestone 7: Advanced Comparison Features (Not started)
- Moved lines detection + manual alignment tools - Not started
- Structured compare modes (XML/CSV/JSON/logical sections) - Not started
- Patch create/apply/preview workflows - Not started
- Rich report exports (HTML/XML/CSV/Text/Patch) - Not started
- Horizontal/vertical layout toggle + compare macros/scripting - Not started
- Remote sources (FTP/SFTP) + VCS browsing (if in scope) - Not started
- Unicode/casing/datetime normalization toggles - Not started
