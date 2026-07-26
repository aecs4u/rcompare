# WinMerge Feature Parity Plan

This document tracks the implementation of WinMerge features in RCompare to achieve feature parity with the popular Windows diff/merge tool.

## Reference

- [WinMerge Official Site](https://winmerge.org/)
- [WinMerge GitHub Repository](https://github.com/WinMerge/winmerge)
- [WinMerge Manual - File Comparison](https://manual.winmerge.org/en/Compare_files.html)
- [WinMerge Manual - Folder Comparison](https://manual.winmerge.org/en/Compare_dirs.html)

## Feature Comparison Matrix

### Already Implemented in RCompare ✅

| Feature | RCompare Status | Notes |
|---------|----------------|-------|
| **Two-way file comparison** | ✅ Complete | Line-by-line diff with Similar crate |
| **Two-way folder comparison** | ✅ Complete | Recursive directory scanning |
| **Syntax highlighting** | ✅ Complete | Via syntect crate |
| **Image comparison** | ✅ Complete | Pixel-level with multiple modes |
| **CSV/Table comparison** | ✅ Complete | Row-by-row, column-aware |
| **Excel comparison** | ✅ Complete | Sheet, row, and cell-level |
| **JSON comparison** | ✅ Complete | Path-based structural diff |
| **YAML comparison** | ✅ Complete | Structural analysis |
| **Archive support** | ✅ Complete | ZIP, TAR, TAR.GZ, 7Z |
| **Binary/hex comparison** | ✅ Complete | Byte-level hex view |
| **Unicode support** | ✅ Complete | Native Rust UTF-8 support |
| **Pattern filtering** | ✅ Complete | Gitignore-compatible patterns |
| **Copy operations** | ✅ Complete | Copy left/right in GUI |
| **Inline diff highlighting** | ✅ Complete | Character-level differences |
| **Progress indicators** | ✅ Complete | Progress bars with ETA |
| **GUI interface** | ✅ Complete | Slint-based UI |
| **CLI interface** | ✅ Complete | Full-featured command-line tool |
| **Text: Ignore whitespace** | ✅ Complete | 5 whitespace handling modes |
| **Text: Ignore case** | ✅ Complete | Case-insensitive comparison |
| **Text: Regex rules** | ✅ Complete | Pattern-based preprocessing |
| **Text: Line ending normalization** | ✅ Complete | CRLF/LF/CR unification |
| **Image: EXIF metadata** | ✅ Complete | Compare camera settings, GPS, timestamps |
| **Image: Tolerance adjustment** | ✅ Complete | Configurable pixel difference threshold |

### Planned (Already in Roadmap) 🔜

| Feature | Priority | Target Phase | Notes |
|---------|----------|--------------|-------|
| **Three-way merge** | High | Phase 7 | Compare base + 2 modifications |
| **Synchronized scrolling** | Medium | Phase 6 | GUI enhancement |
| **Location/diff map pane** | Medium | Phase 6 | Visual diff overview |
| **Conflict resolution UI** | High | Phase 7 | Interactive merge UI |

### Missing from RCompare (New Work) ❌

#### 1. Version Control Integration 🔴 High Priority

**Description:** Direct integration with version control systems to compare working directory, staged changes, commits, and branches.

**Supported VCS:**
- Git (most important)
- Subversion (SVN)
- Mercurial (Hg)

**Features:**
- Compare working directory vs HEAD
- Compare two commits
- Compare two branches
- Show commit history with diff preview
- Blame/annotate view
- Stage/unstage hunks directly
- Resolve merge conflicts

**Implementation Notes:**
- Use `git2` crate for Git integration
- Consider `libsvn` or command-line wrappers for SVN
- Command-line wrappers for Mercurial
- Add VCS detection to scanner
- New "VCS" menu in GUI
- CLI commands: `rcompare git diff`, `rcompare git compare-commits`, etc.

**Estimated Effort:** 2-3 weeks

---

#### 2. Shell Integration 🔴 High Priority

**Description:** Context menu integration in file managers for quick access to comparison.

**Platforms:**
- **Linux:** Nautilus, Dolphin, Thunar, Nemo
- **Windows:** Windows Explorer
- **macOS:** Finder

**Features:**
- Right-click file/folder → "Compare with RCompare"
- Select two items → "Compare in RCompare"
- "Compare with..." → Select comparison target
- Send to RCompare from command palette

**Implementation Notes:**
- Linux: Desktop entry files, Nautilus Python extensions
- Windows: Registry entries, COM interfaces
- macOS: Finder Sync extensions
- Separate installer/setup script
- Add `--register-shell` CLI command

**Estimated Effort:** 1-2 weeks per platform

---

#### 3. Advanced Folder Filtering 🟡 Medium Priority

**Description:** More sophisticated filtering beyond gitignore patterns.

**Filter Types:**
- **Attribute-based:**
  - File size (min/max, ranges)
  - Modification date (before/after, ranges)
  - File type/extension
  - Regex on full path
  - Regex on file content
- **Logical operators:**
  - AND, OR, NOT combinations
  - Filter presets (e.g., "Only images", "Only code files")
- **Exclusion lists:**
  - Temporary files
  - Build artifacts
  - Version control files

**Implementation Notes:**
- Create `FilterExpression` enum with AST
- Parser for filter language
- GUI filter builder interface
- Save/load filter presets
- Update FolderScanner to support attribute filtering

**Estimated Effort:** 1 week

---

#### 4. Interactive Merge Mode 🟡 Medium Priority

**Description:** Edit files directly in the diff view and merge changes interactively.

**Features:**
- Edit left/right panes directly
- Copy selection left→right or right→left
- Copy line/block with keyboard shortcuts
- Merge all from left/right
- Resolve conflicts by choosing sides
- Save merged result
- Undo/redo merge operations

**Implementation Notes:**
- Make diff view editable
- Track merge operations for undo
- Add "Merge" mode to GUI (separate from "Compare")
- Keyboard shortcuts: Ctrl+Shift+← / →
- Warning on unsaved changes
- Integration with VCS for conflict resolution

**Estimated Effort:** 2 weeks

---

#### 5. Plugin System 🟢 Low Priority

**Description:** Extensibility system for custom file comparisons and transformations.

**Plugin Types:**
- **File comparators:** Custom diff algorithms for specific file types
- **Preprocessors:** Transform files before comparison (e.g., prettify, normalize)
- **Filters:** Custom filtering logic
- **Exporters:** Custom output formats

**Implementation Notes:**
- Use WASM plugins for sandboxing
- Define plugin trait/interface
- Plugin discovery mechanism
- Plugin configuration UI
- Example plugins: PDF compare, XML prettify, minified JS expansion

**Estimated Effort:** 3 weeks

---

#### 6. Folder Synchronization 🟡 Medium Priority

**Description:** Advanced synchronization with detailed options and dry-run.

**Current Status:** Basic copy operations exist in GUI

**Missing Features:**
- Sync profiles with rules
- Preview sync operations
- Bidirectional sync with conflict detection
- Mirror mode (make target identical to source)
- Update mode (only copy newer files)
- Custom sync rules per folder/file pattern
- Sync history/log
- Scheduled sync (cron-like)

**Implementation Notes:**
- Extend existing sync dialog
- Add `SyncProfile` configuration
- Implement sync engine with transaction log
- Add `--sync` CLI mode with options
- Safety: require confirmation for destructive ops

**Estimated Effort:** 1-2 weeks

---

#### 7. Bookmarks and Sessions 🟢 Low Priority

**Description:** Save comparison sessions and quick-access bookmarks.

**Current Status:** Basic profile saving exists

**Missing Features:**
- Bookmark specific file pairs
- Recent comparisons list
- Session restoration on startup
- Named comparison profiles
- Quick-switch between sessions
- Session history with timestamps

**Implementation Notes:**
- Extend existing SessionProfile in types.rs
- Add session manager to GUI
- Persist session state (scroll position, filters, etc.)
- CLI: `--session <name>` to load saved session

**Estimated Effort:** 3-4 days

---

#### 8. Report Generation 🟡 Medium Priority

**Description:** Generate comparison reports in various formats.

**Current Status:** JSON output exists

**Missing Features:**
- HTML report with embedded diffs
- PDF report generation
- Markdown report
- XML report
- Statistics summary (charts/graphs)
- Customizable report templates
- Email report functionality

**Implementation Notes:**
- Create report generation module
- Use `printpdf` for PDF, templating for HTML
- Add `--report` CLI option with format selection
- GUI: "Export Report" menu
- Include diff snippets in reports

**Estimated Effort:** 1 week

---

#### 9. Line Number Alignment 🟢 Low Priority

**Description:** Options for how line numbers are displayed in diff view.

**Options:**
- Show original line numbers
- Show unified line numbers
- Show both
- Hide line numbers
- Jump to line by number

**Implementation Notes:**
- Update text diff view in GUI
- Add line number column configuration
- Implement "Go to Line" dialog

**Estimated Effort:** 2-3 days

---

#### 10. Whitespace Handling ✅ **COMPLETED**

**Description:** Options for ignoring various whitespace differences.

**Implemented Options:**
- ✅ Ignore all whitespace (`WhitespaceMode::IgnoreAll`)
- ✅ Ignore leading whitespace (`WhitespaceMode::IgnoreLeading`)
- ✅ Ignore trailing whitespace (`WhitespaceMode::IgnoreTrailing`)
- ✅ Ignore whitespace changes (`WhitespaceMode::IgnoreChanges`)
- ✅ Normalize line endings (CRLF/LF/CR → LF)
- ✅ Tab width configuration (configurable, default: 4)

**Implementation:** [rcompare_core/src/text_diff.rs](../rcompare_core/src/text_diff.rs)

**Status:** Completed in Phase 1

---

#### 11. Grammar-Aware Text Comparison 🔴 **DEFERRED** (Phase 3+)

**Description:** AST-based (Abstract Syntax Tree) comparison that understands programming language syntax and semantics rather than comparing text line-by-line.

**Goals:**
- Recognize equivalent code that differs only in formatting
- Detect moved functions/methods
- Understand refactorings (e.g., variable renames)
- Ignore syntactically irrelevant changes (e.g., comment reformatting)
- Provide semantic diff output

**Research Findings (2026-01-26):**

The Rust ecosystem has two major tools for grammar-aware diffing:

1. **[Diffsitter](https://github.com/afnanenayet/diffsitter)** - Tree-sitter based AST difftool
   - Uses tree-sitter parsers for 13+ languages
   - Leaf-node filtering with include/exclude rules
   - Standalone CLI tool, not designed as a library

2. **[Difftastic](https://github.com/Wilfred/difftastic)** - Structural diff tool
   - Uses Dijkstra's algorithm for structural diffing
   - Supports 30+ languages via tree-sitter
   - Handles syntax, ignores insignificant whitespace
   - Written in Rust but primarily a CLI tool

**Implementation Requirements:**
- Add `tree-sitter` crate (core parsing library)
- Add language-specific grammar crates:
  - `tree-sitter-rust` for Rust
  - `tree-sitter-python` for Python
  - `tree-sitter-javascript` for JS/TS
  - Additional grammars as needed (30+ available)
- Implement AST diffing algorithm (e.g., Dijkstra's approach)
- Create AST node mapping and comparison logic
- Add UI for displaying structural diffs
- CLI flags for enabling grammar-aware mode

**Challenges:**
- **Complexity:** Requires full AST parsing and structural diff algorithms
- **Language Support:** Each language needs its own grammar
- **Performance:** AST parsing is 2-3x slower than lexical parsing
- **Integration:** diffsitter/difftastic are standalone tools, not libraries
- **Development Time:** Estimated 4-6 weeks for initial implementation

**Decision:** Defer to Phase 3 or later due to complexity. Phase 1 focused on simpler preprocessing options (whitespace, case, regex) that provide significant value with minimal complexity.

**Alternative Approach:** Consider integrating difftastic as an external tool via CLI wrapper for grammar-aware comparisons, similar to how Git integrates external diff tools.

**References:**
- [diffsitter](https://github.com/afnanenayet/diffsitter) - Tree-sitter based AST difftool
- [difftastic](https://github.com/Wilfred/difftastic) - Structural diff with Dijkstra's algorithm
- [tree-sitter crate](https://crates.io/crates/tree-sitter) - Rust bindings
- [Using Tree-sitter Parsers in Rust](https://rfdonnelly.github.io/posts/using-tree-sitter-parsers-in-rust/)

**Estimated Effort:** 4-6 weeks for initial implementation with 5-10 language support

---

#### 12. Editable Hex Mode 🟡 **DEFERRED** (Phase 7)

**Description:** Allow users to edit binary files directly in the hex view, similar to dedicated hex editors like HxD or 010 Editor.

**Goals:**
- In-place hex byte editing
- Insert/delete bytes
- Copy/paste hex data
- Undo/redo operations
- Save modified files
- Search and replace in hex
- Highlight edited bytes

**Research Findings (2026-01-26):**

The Rust ecosystem has several hex editor crates:

1. **[hex-patch](https://crates.io/crates/hex-patch)** - Terminal hex editor (v1.12.4)
   - Binary patcher and editor with TUI
   - Disassembles instructions and assembles patches
   - Supports various architectures and file formats
   - Can edit remote files via SSH
   - Most feature-rich option

2. **[rex](https://github.com/dbrodie/rex)** - Terminal hex editor
   - Focuses on insert/delete in the middle of files
   - Easy selection and copy/paste
   - Alpha stage, requires backups

3. **[hexdino](https://crates.io/crates/hexdino)** - Vim-like hex editor
   - Vim keybindings
   - Terminal-based

**Current RCompare Status:**
- Hex viewing is read-only (see `rcompare_core/src/binary_diff.rs`)
- GUI displays hex in `HexDiffLine` structures (Slint UI)
- No editing capabilities

**Implementation Requirements:**
- **Core Functionality:**
  - Add byte modification tracking to `BinaryDiffEngine`
  - Implement edit buffer with undo/redo stack
  - File write operations with backup
  - Validation of hex input (0x00-0xFF)

- **GUI Changes:**
  - Convert `HexDiffLine` text displays to editable fields
  - Add edit mode toggle (view vs edit)
  - Highlight modified bytes in different color
  - Show unsaved changes indicator
  - Add save/save-as/revert buttons
  - Implement hex input validation in Slint

- **Safety Features:**
  - Automatic backup before editing
  - Confirmation dialogs for saves
  - File locking to prevent concurrent edits
  - Maximum file size limits (prevent editing huge files)

**Challenges:**
- **GUI Complexity:** Slint doesn't have built-in hex editor widgets
  - Would need custom text input widgets with hex validation
  - Complex keyboard navigation (arrow keys, tab, etc.)
  - Selection and copy/paste in hex format

- **Performance:** Large file editing requires careful memory management
  - Need efficient edit buffer (gap buffer or piece table)
  - Lazy loading for large files

- **File Safety:** Risk of corrupting binary files
  - Must implement robust backup mechanism
  - Validate all operations before writing

**Decision:** Defer to Phase 7. The current read-only hex view is sufficient for comparison purposes. Editing is a power-user feature that requires significant GUI work and safety mechanisms.

**Alternative Approach:** Add "Open in External Hex Editor" button that launches a dedicated hex editor (HxD, 010 Editor, ImHex, etc.) for files that need editing.

**References:**
- [hex-patch crate](https://crates.io/crates/hex-patch) - Full-featured binary patcher
- [rex](https://github.com/dbrodie/rex) - Lightweight hex editor
- [hex-editor keyword on crates.io](https://crates.io/keywords/hex-editor)

**Estimated Effort:** 2-3 weeks for basic implementation

---

#### 13. Structure Viewer for Binary Files 🟡 **DEFERRED** (Phase 7)

**Description:** Display structured representation of common binary file formats (executables, object files, databases) showing headers, sections, symbols, and metadata.

**Goals:**
- Parse and display ELF file structure (Linux executables)
- Parse and display PE file structure (Windows executables)
- Parse and display Mach-O file structure (macOS executables)
- Show file headers, sections, symbols, imports/exports
- Compare structures side-by-side
- Navigate to specific sections/offsets

**Research Findings (2026-01-26):**

The Rust ecosystem has excellent binary format parsers:

1. **[goblin](https://github.com/m4b/goblin)** - Cross-platform binary parser
   - "An impish, cross-platform binary parsing crate"
   - Supports ELF (32/64-bit), PE (32/64-bit), Mach-O
   - Unix/BSD archive parser
   - Core, std-free `#[repr(C)]` structs
   - Compile-time switch between 32/64-bit
   - Extensively fuzzed (100 million runs)
   - Actively maintained (October 2025)

**Supported Formats:**
- **ELF** (Executable and Linkable Format) - Linux/Unix
  - Program headers, section headers
  - Symbol tables, dynamic symbols
  - Relocations, notes

- **PE** (Portable Executable) - Windows
  - DOS header, PE header, optional header
  - Section table, import/export tables
  - Resource directory

- **Mach-O** (Mach Object) - macOS/iOS
  - Load commands, segments, sections
  - Symbol table, dynamic symbol table

**Implementation Requirements:**
- **Core Functionality:**
  - Add `goblin` crate dependency
  - Create `StructuredBinaryView` module
  - Parse files using goblin
  - Extract structure information (headers, sections, symbols)
  - Compare structures between left/right files

- **GUI Changes:**
  - New view mode: "Structure View" (add to active-view enum)
  - Tree widget showing hierarchical structure
  - Expandable/collapsible sections
  - Details panel for selected structure element
  - Highlight differences between left/right structures

- **Display Information:**
  - **Headers:** File type, architecture, entry point, flags
  - **Sections:** Name, offset, size, permissions, alignment
  - **Symbols:** Name, address, size, type, binding
  - **Imports/Exports:** Library dependencies, exported functions
  - **Metadata:** Build ID, debug info, version info

**Use Cases:**
- **Binary Comparison:** Compare compiled versions of same code
- **Library Updates:** Check symbol compatibility
- **Debug Info:** Verify debug symbols in release builds
- **Security Analysis:** Examine executable structure
- **Reverse Engineering:** Understand binary layout

**Challenges:**
- **Format Complexity:** Binary formats are complex with many edge cases
  - PE files have dozens of structures
  - ELF has multiple versions and extensions

- **GUI Design:** Displaying hierarchical binary structures is complex
  - Need tree view widget in Slint
  - Side-by-side comparison with alignment
  - Highlighting differences in structures

- **Performance:** Large binaries with thousands of symbols
  - Need lazy loading and pagination
  - Efficient diff algorithm for structures

**Decision:** Defer to Phase 7. This is a specialized feature mainly useful for developers comparing compiled binaries. The current hex view provides basic binary comparison capabilities.

**Alternative Approach:**
- Add "Analyze with External Tool" that exports to JSON
- Users can use dedicated tools like `readelf`, `objdump`, `dumpbin`
- Focus on core comparison features first

**References:**
- [goblin crate](https://github.com/m4b/goblin) - Cross-platform binary parser
- [goblin documentation](https://docs.rs/goblin)
- [lib.rs/crates/goblin](https://lib.rs/crates/goblin)

**Estimated Effort:** 2-3 weeks for basic implementation with ELF/PE/Mach-O support

---

## Implementation Roadmap

### Phase 1: Quick Wins (1-2 weeks) ✅ **COMPLETED**
- [ ] Advanced folder filtering (deferred to Phase 5)
- [x] Whitespace handling options (5 modes implemented)
- [x] Case-insensitive comparison
- [x] Regular expression rules
- [x] EXIF metadata comparison
- [x] Image tolerance adjustment
- [ ] Line number alignment (deferred to Phase 6)
- [ ] Bookmarks and sessions enhancement (deferred to Phase 6)
- [ ] Grammar-aware text comparison (deferred to Phase 7 - requires AST parsing)

### Phase 2: VCS Integration (3-4 weeks)
- [ ] Git integration (CLI)
- [ ] Git integration (GUI)
- [ ] Basic SVN support
- [ ] Conflict resolution workflow

### Phase 3: Shell Integration (2-3 weeks)
- [ ] Linux file manager integration
- [ ] Windows Explorer integration
- [ ] macOS Finder integration

### Phase 4: Advanced Merging (2-3 weeks)
- [ ] Interactive merge mode
- [ ] Three-way merge (from existing roadmap)
- [ ] Conflict resolution UI (from existing roadmap)

### Phase 5: Sync & Reports (2 weeks)
- [ ] Folder synchronization enhancement
- [ ] Report generation

### Phase 6: Extensibility (3-4 weeks)
- [ ] Plugin system design
- [ ] Plugin API implementation
- [ ] Example plugins
- [ ] Plugin documentation

### Phase 7: Advanced Text & Binary Comparison (4-6 weeks)
- [ ] Grammar-aware text comparison with tree-sitter
  - [ ] Rust language support
  - [ ] Python language support
  - [ ] JavaScript/TypeScript support
  - [ ] Additional languages as needed
- [ ] Editable hex mode for binary comparison
- [ ] Structure viewer for binary files
- [ ] AST-based diff visualization

## Priority Legend

- 🔴 **High Priority:** Essential for feature parity, high user demand
- 🟡 **Medium Priority:** Important but not critical
- 🟢 **Low Priority:** Nice to have, can be deferred

## Notes

### Out of Scope

The following WinMerge features are intentionally out of scope for RCompare:

1. **Visual SourceSafe integration:** Legacy VCS, not relevant
2. **Windows-specific APIs:** RCompare is cross-platform
3. **Proprietary file formats:** Focus on open standards

### RCompare Advantages Over WinMerge

RCompare already has some features that WinMerge lacks or has limited support for:

1. **Parquet file comparison:** DataFrame-level analysis
2. **Modern archive formats:** Native 7z support
3. **Remote filesystems:** S3, SFTP, WebDAV (CLI)
4. **Cross-platform:** Native Linux and macOS support
5. **Modern UI framework:** Slint vs Win32
6. **Performance:** Rust + BLAKE3 + parallel processing
7. **Hash caching:** Persistent cache across sessions
8. **Advanced text comparison:** 5 whitespace modes, regex rules, case-insensitive
9. **EXIF metadata comparison:** Full camera metadata analysis for images
10. **Configurable image tolerance:** Fine-grained pixel difference control

## Contributing

To contribute to WinMerge parity features:

1. Check this document for feature status
2. Create a feature branch: `git checkout -b feature/winmerge-<feature-name>`
3. Implement the feature following [ARCHITECTURE.md](../ARCHITECTURE.md)
4. Update this document with progress
5. Submit a pull request

---

**Last Updated:** 2026-01-26
**Branch:** feature/winmerge-parity
