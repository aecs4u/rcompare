# RCompare Quick Start Guide

## What is RCompare?

RCompare is a high-performance file and directory comparison tool written in Rust. It provides both command-line and graphical interfaces for comparing folders, detecting differences, and identifying orphaned files.

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/aecs4u/rcompare
cd rcompare

# Build release binaries
cargo build --release

# Binaries will be in target/release/
# - rcompare_cli (4.6 MB)
# - rcompare_gui (21 MB)
```

### Install Locally

```bash
# Install CLI
cargo install --path rcompare_cli

# Install GUI
cargo install --path rcompare_gui
```

## Using the CLI

### Basic Comparison

Compare two directories:

```bash
rcompare_cli scan /path/to/left /path/to/right
```

### Example Output

```
================================================================================
Comparison Results
================================================================================
  ==   file1.txt        (Identical)
  !=   file2.txt        (Different content)
  <<   file3.txt        (Left only)
  >>   file4.txt        (Right only)

================================================================================
Summary:
  Total files:     4
  Identical:       1 (==)
  Different:       1 (!=)
  Left only:       1 (<<)
  Right only:      1 (>>)
================================================================================
```

### Advanced Options

```bash
# Ignore specific patterns
rcompare_cli scan /left /right -i "*.o" -i "*.tmp" -i "node_modules/"

# Show only differences (hide identical files)
rcompare_cli scan /left /right --diff-only

# Enable hash verification for same-sized files
rcompare_cli scan /left /right --verify-hashes

# Use custom cache directory
rcompare_cli scan /left /right --cache-dir /path/to/cache

# Follow symbolic links
rcompare_cli scan /left /right -L
```

## Using the GUI

RCompare provides two graphical interfaces:
- **Slint GUI** (rcompare_gui): Native, lightweight, cross-platform
- **PySide6 GUI** (Python frontend): Feature-rich with advanced diff viewers

### Slint GUI (Native)

#### Launch the GUI

```bash
rcompare_gui
```

#### GUI Features

1. **Select Directories**: Click "Select Left..." and "Select Right..." to choose directories
2. **Compare**: Click the "Compare" button to run the comparison
3. **View Results**: Files are displayed side-by-side with color coding:
   - 🟢 Green background: Identical files
   - 🔴 Red background: Different files
   - 🟡 Yellow background: Left only
   - 🔵 Blue background: Right only
4. **Status Bar**: Shows summary statistics at the bottom
5. **Refresh**: Click "Refresh" to re-run the comparison

### PySide6 GUI (Python Frontend)

The PySide6 frontend provides advanced features including specialized diff viewers for text, images, CSV, Excel, JSON, and binary files.

#### Installation

```bash
# Install Python dependencies
pip install PySide6 Pillow openpyxl

# Or use requirements file (if available)
pip install -r frontend/requirements.txt
```

#### Launch the PySide6 GUI

```bash
# From the repository root
python frontend/main.py

# Or if installed as a package
rcompare-pyside6
```

#### PySide6 Features

1. **Directory Comparison**: Full directory tree comparison with expand/collapse
2. **Specialized Diff Viewers**:
   - **Text Diff**: Line-by-line comparison with syntax highlighting
   - **Image Diff**: Side-by-side image comparison with pixel differences
   - **CSV Diff**: Row/column comparison for CSV files
   - **Excel Diff**: Sheet and cell-level comparison
   - **JSON/YAML Diff**: Structural comparison with formatting
   - **Binary Diff**: Hex viewer for binary files
3. **File Operations**: Copy left/right with progress tracking
4. **Export**: JSON output for automation and scripting
5. **Settings**: Configurable comparison options and display preferences

## C/C++ Integration (FFI)

RCompare provides a C-compatible Foreign Function Interface (FFI) for integrating patch parsing and manipulation into C/C++ applications. This is particularly useful for KDE applications and other C++ projects that need libkomparediff2-compatible functionality.

### Building the FFI Library

```bash
# Build the static library
cargo build --package rcompare_ffi --release

# Library location:
# Linux/macOS: target/release/librcompare_ffi.a
# Windows:     target/release/rcompare_ffi.lib

# Header file:
# rcompare_ffi/include/rcompare.h
```

### Basic C Example

```c
#include "rcompare.h"
#include <stdio.h>
#include <string.h>

int main(void) {
    const char* diff_text =
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n";

    // Parse diff
    PatchSetHandle* handle = NULL;
    int result = rcompare_parse_diff(
        (const uint8_t*)diff_text,
        strlen(diff_text),
        &handle
    );

    if (result != 0) {
        fprintf(stderr, "Parse failed\n");
        return 1;
    }

    // Access metadata
    size_t file_count = rcompare_patchset_file_count(handle);
    printf("Files: %zu\n", file_count);

    // Cleanup
    rcompare_free_patchset(handle);
    return 0;
}
```

### CMake Integration

```cmake
# Add RCompare FFI to your project
add_subdirectory(path/to/rcompare/rcompare_ffi)

# Link to your target
target_link_libraries(your_target PRIVATE rcompare)
```

### FFI Features

- **Parse multiple diff formats**: Unified, context, normal, RCS, ed
- **Auto-detect generators**: CVS, Perforce, Subversion, plain diff
- **Patch operations**: Apply/unapply individual or all differences
- **File blending**: Merge original file content with patch hunks
- **Serialization**: Convert patch model back to unified diff format
- **Memory safe**: Opaque handle pattern with proper lifetime management

### Documentation

For complete API reference and examples, see:
- [rcompare_ffi/README.md](rcompare_ffi/README.md)
- [rcompare_ffi/include/rcompare.h](rcompare_ffi/include/rcompare.h)
- C examples: `rcompare_ffi/examples/`

## Understanding the Output

### Status Symbols (CLI)

- `==` : Files are identical (same size, timestamp, and content)
- `!=` : Files differ in content
- `<<` : File exists only on the left side (orphan)
- `>>` : File exists only on the right side (orphan)
- `??` : Files have same size but not verified (use --verify-hashes)

### Color Coding (GUI)

- **Light Green**: Identical files
- **Light Red**: Different files
- **Light Yellow**: Left-only files
- **Light Blue**: Right-only files
- **Gray**: Unchecked files

## Performance Tips

### Hash Cache

RCompare automatically caches file hashes to avoid re-computing them:

- **Linux**: `~/.cache/rcompare/`
- **Windows**: `%LOCALAPPDATA%\rcompare\cache\`
- **macOS**: `~/Library/Caches/rcompare/`

The cache stores:
- File path
- Modification time
- File size
- BLAKE3 hash

Files are only re-hashed if their size or modification time changes.

### Large Directory Trees

For best performance with large directories:

1. Use ignore patterns to exclude unnecessary directories
2. Let the hash cache build up over time
3. The scanner uses parallel traversal automatically

### Memory Usage

RCompare keeps file metadata in memory during comparison. For very large directories (1M+ files), expect memory usage of approximately:

- **Typical**: 100-200 bytes per file
- **Example**: 1 million files ≈ 100-200 MB RAM

## Use Cases

### Backup Verification

```bash
# Compare backup with source
rcompare_cli scan /source /backup --verify-hashes
```

### Code Synchronization

```bash
# Check local vs remote code, ignoring build artifacts
rcompare_cli scan /local/project /remote/project \
  -i "*.o" -i "*.so" -i "target/" -i "node_modules/"
```

### Deployment Validation

```bash
# Ensure deployed files match build artifacts
rcompare_cli scan /build/output /var/www/html --diff-only
```

### Directory Deduplication

```bash
# Find duplicate directory structures
rcompare_cli scan /downloads/set1 /downloads/set2
```

## Configuration

### Environment Variables

```bash
# Set custom cache directory
export RCOMPARE_CACHE_DIR=/path/to/cache

# Enable debug logging
export RUST_LOG=debug
rcompare_cli scan /left /right
```

### Ignore Patterns

Create a `.rcompare.ignore` file (future feature):

```
# Ignore build artifacts
*.o
*.so
*.dll
target/
build/

# Ignore dependencies
node_modules/
vendor/

# Ignore temporary files
*.tmp
*.swp
.DS_Store
```

## Troubleshooting

### "Permission denied" errors

Run with appropriate permissions or use `sudo` for system directories.

### Cache grows too large

Clear the cache manually:

```bash
# Linux/macOS
rm -rf ~/.cache/rcompare/

# Windows
rmdir /s %LOCALAPPDATA%\rcompare\cache\
```

### GUI doesn't start

Ensure you have the required graphics libraries:

```bash
# Linux (Ubuntu/Debian)
sudo apt install libfontconfig1-dev libxcb-shape0-dev libxcb-xfixes0-dev

# Fedora
sudo dnf install fontconfig-devel libxcb-devel
```

### Slow performance

1. Check if you're comparing network drives (slower I/O)
2. Use ignore patterns to exclude unnecessary directories
3. Disable hash verification if not needed
4. Use SSD instead of HDD for cache directory

## Keyboard Shortcuts (GUI - Future)

- `Ctrl+L`: Select left directory
- `Ctrl+R`: Select right directory
- `Ctrl+Enter`: Run comparison
- `F5`: Refresh
- `Ctrl+Q`: Quit

## Command Reference

### CLI Commands

```bash
rcompare_cli scan <LEFT> <RIGHT> [OPTIONS]

OPTIONS:
  -i, --ignore <PATTERN>        Ignore patterns (can be repeated)
  -L, --follow-symlinks         Follow symbolic links
  -v, --verify-hashes           Verify file hashes for same-sized files
  -c, --cache-dir <DIR>         Cache directory for hash storage
  -d, --diff-only               Show only differences (hide identical files)
  -h, --help                    Print help
  -V, --version                 Print version
```

## Examples

### Example 1: Basic Backup Check

```bash
# Compare backup with source
rcompare_cli scan ~/Documents ~/Backup/Documents
```

### Example 2: Web Deployment

```bash
# Verify website deployment
rcompare_cli scan ./dist /var/www/html \
  --diff-only \
  --verify-hashes
```

### Example 3: Project Sync

```bash
# Check if projects are in sync, ignore build artifacts
rcompare_cli scan \
  ~/dev/project \
  /mnt/remote/project \
  -i "target/" \
  -i "*.o" \
  -i ".git/" \
  --diff-only
```

### Example 4: Photo Library Deduplication

```bash
# Find duplicate photos in different folders
rcompare_cli scan \
  ~/Photos/2023 \
  ~/Photos/Backup/2023 \
  --verify-hashes
```

## Getting Help

- **Documentation**: See [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- **Development Status**: See [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md)
- **Issues**: Report bugs on GitHub
- **CLI Help**: `rcompare_cli --help`

## Current Features

RCompare currently provides:

### Core Comparison Engine
- ✅ BLAKE3 hashing with persistent cache
- ✅ Parallel directory traversal
- ✅ Gitignore pattern support
- ✅ Cross-platform support (Linux, Windows, macOS)

### Specialized Format Support
- ✅ Text diff viewer with syntax highlighting
- ✅ Archive comparison (ZIP, TAR, 7Z)
- ✅ Binary hex viewer
- ✅ Image comparison with pixel diff
- ✅ CSV and Excel comparison
- ✅ JSON and YAML structural diff
- ✅ Parquet DataFrame comparison

### Patch System
- ✅ Multi-format diff parser (unified, context, normal, RCS, ed)
- ✅ Patch apply/unapply operations
- ✅ File blending with original content
- ✅ C/C++ FFI layer (libkomparediff2-compatible)

### User Interfaces
- ✅ CLI with progress indicators and JSON output
- ✅ Native Slint GUI
- ✅ PySide6 GUI with specialized viewers
- ✅ Copy operations (left/right)

## What's Next?

Future enhancements planned:

### Phase 4: Performance & GUI (In Progress)
- 🚧 Parallel hash computing (2-3x speedup)
- 📋 Three-way merge
- 📋 Tabs for multiple comparisons
- 📋 Synced scrolling with diff map

### Phase 5: Reporting & Workflow
- 📋 HTML/Markdown/CSV report export
- 📋 JUnit XML for CI integration
- 📋 Diff statistics dashboard
- 📋 Comparison presets (save/load)

### Phase 6-7: Cloud & Advanced
- 📋 Additional cloud providers (GCS, Azure, Dropbox)
- 📋 Watch mode for continuous monitoring
- 📋 Semantic diff (AST-based)
- 📋 Plugin/extension system

See [ROADMAP.md](ROADMAP.md) for detailed development timeline.

---

**Version**: 0.3.0-dev
**Last Updated**: 2026-01-30
**License**: MIT OR Apache-2.0
