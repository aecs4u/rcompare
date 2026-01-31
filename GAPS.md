# Known Gaps and Limitations

This document tracks known limitations, gaps, and areas for improvement in RCompare.

Last updated: 2026-01-30

---

## Performance

### ✅ Parallel Hash Computing (Completed)
**Status**: Implemented in Phase 4
**Impact**: High - 2-3x performance improvement achieved

**Implementation**:
- Multi-threaded BLAKE3 hashing with rayon work-stealing
- `hash_files_parallel()` API for batch operations
- Adaptive buffer sizing (64KB → 1MB for large files)
- Progress callback support for real-time updates

**Performance**:
- Baseline: ~3GB/s (single-threaded)
- Parallel: 6-9GB/s on 4-8 core systems
- Best for medium-to-large files (>1MB)

### ✅ Streaming Large File Comparison (Completed)
**Status**: Implemented in Phase 4
**Impact**: Medium - Critical for 1GB+ files

**Implementation**:
- Chunk-by-chunk comparison (1MB chunks)
- Configurable streaming threshold (default: 100MB)
- Early exit on first chunk mismatch for performance
- Zero memory overhead beyond chunk buffers
- Automatic fallback for files below threshold

**API**:
```rust
let engine = ComparisonEngine::new(cache)
    .with_streaming_threshold(100 * 1024 * 1024); // 100MB threshold
```

**Performance**:
- Memory usage: Constant ~2MB (two 1MB buffers)
- No file size limitations
- Suitable for multi-GB file comparisons
- Early exit optimization for different files

### SQLite Index for Very Large Trees
**Status**: Not implemented  
**Impact**: Medium - Important for 1M+ files

**Current State**:
- All comparison results in memory
- HashMap-based storage
- Memory usage: ~100-200 bytes per file

**Planned Solution**:
- Optional SQLite backend for large comparisons
- Fast filtering and sorting
- Persistent comparison state
- Query-based result access

---

## CLI

### ✅ Exit Codes (Completed)
**Status**: Fully implemented
**Impact**: Low - CI integration use case

**Implementation**:
- Exit 0: No differences found (directories identical)
- Exit 1: Error occurred (invalid paths, I/O errors, etc.)
- Exit 2: Differences found between directories

**Usage**:
```bash
rcompare_cli scan /source /backup
case $? in
  0) echo "✓ Identical" ;;
  2) echo "⚠ Differences found" ;;
  *) echo "✗ Error" ;;
esac
```

Documented in QUICKSTART.md with scripting examples.

### Integration Tests for Specialized Formats
**Status**: Basic coverage only  
**Impact**: Medium - Test quality

**Current State**:
- Basic directory comparison tests
- No tests for CSV/Excel/JSON/Parquet/Image comparisons
- Limited archive comparison tests

**Needed**:
- End-to-end tests for each specialized format
- Edge case coverage (malformed files, encoding issues)
- Performance regression tests

---

## GUI

### Synced Scrolling
**Status**: Not implemented  
**Impact**: Medium - UX improvement

**Description**: Left and right file trees should scroll in sync with visual indicators showing alignment.

**Implementation**:
- Synchronized scroll events
- Gutter diff map visualization
- Click-to-navigate from gutter

### Tabs for Multiple Comparisons
**Status**: Not implemented  
**Impact**: Medium - Power user feature

**Description**: Multi-document interface for comparing multiple directory pairs simultaneously.

**Implementation**:
- Tab widget in Slint
- Tab persistence across sessions
- Keyboard shortcuts (Ctrl+Tab, etc.)

### ✅ Three-Way Merge (Completed - Core)
**Status**: Core logic implemented in Phase 4
**Impact**: High - Advanced workflow

**Description**: Compare base, left, and right versions for merge conflict resolution.

**Implementation**:
- ✅ Core merge engine in rcompare_core
  - `MergeEngine` with conflict detection
  - Auto-merge for non-conflicting changes
  - Comprehensive conflict type detection
  - 12 tests covering all scenarios
- 📋 Three-pane GUI layout (pending)
- 📋 Conflict detection and resolution UI (pending)

**API**:
```rust
use rcompare_core::MergeEngine;
use std::collections::HashMap;

let engine = MergeEngine::new();
let results = engine.merge(&base, &left, &right)?;

for result in results {
    match result.resolution {
        MergeResolution::UseLeft => // Auto-resolved: use left
        MergeResolution::UseRight => // Auto-resolved: use right
        MergeResolution::AutoMerged => // Both changed to same
        MergeResolution::ManualRequired => // Conflict needs resolution
        MergeResolution::UseBase => // Both deleted or unchanged
    }
}
```

**Conflict Detection**:
- BothModified: Both sides modified the same file differently
- ModifyDelete: Modified on one side, deleted on other
- BothAdded: Added on both sides with different content
- TypeConflict: Directory vs file conflict

**Performance**:
- O(n) where n = unique paths across all three trees
- Constant memory per file (metadata only)
- Size/timestamp comparison (no content hashing in merge logic)

---

## Copy Operations

### ✅ Post-Copy Verification (Completed)
**Status**: Implemented in Phase 4
**Impact**: Medium - Data integrity

**Implementation**:
- BLAKE3 hash verification with adaptive buffer sizing
- Source hash computed before copy
- Destination hash computed after copy
- Automatic hash comparison and mismatch detection
- Configurable retry logic for failed copies (up to N retries)
- Corrupted files automatically deleted and retried
- Comprehensive test coverage

**API**:
```rust
let ops = FileOperations::with_verification(
    dry_run: false,
    use_trash: false,
    verify: true,
    max_retries: 3
);
let result = ops.copy_file(&source, &dest)?;
assert!(result.verified);
assert_eq!(result.source_hash, result.dest_hash);
```

### Resumable Copies
**Status**: Not implemented  
**Impact**: Medium - Large file transfers

**Description**: Resume interrupted copy operations from where they left off.

**Implementation**:
- Track copy progress in database
- Partial file support
- Resume from last checkpoint
- Cleanup on completion

---

## Archives

### Streaming 7Z Support
**Status**: Limited - extraction-based only  
**Impact**: Low - Performance for large 7Z files

**Current State**:
- 7Z files extracted to temp directory
- Full extraction even for partial comparison
- Memory and disk overhead

**Planned Improvement**:
- Direct 7Z stream reading
- Entry-level random access
- No temp directory needed

---

## Reporting

### Export Formats
**Status**: Not implemented  
**Impact**: Medium - Enterprise use case

**Current State**:
- CLI text output with color coding
- ✅ JSON output for automation (schema version 1.1.0)
- ✅ Progress bars for scanning and comparison
- No visual reports

**Completed**:
- JSON schema versioning (v1.1.0)
  - Includes schema_version field
  - Supports specialized diff reports (text, image, CSV, Excel, JSON, YAML, Parquet)
  - Documented version history for compatibility

**Needed**:
- HTML reports (side-by-side diff view)
- Markdown export (GitHub-friendly)
- CSV/Excel reports (statistics)
- JUnit XML (CI integration)

### Diff Statistics Dashboard
**Status**: Not implemented  
**Impact**: Low - Nice to have

**Description**: Visual summary of comparison results with charts and graphs.

**Implementation**:
- File type breakdown chart
- Size distribution histogram
- Change timeline visualization
- Interactive filtering

---

## Cloud Storage

### Provider Coverage
**Status**: Partial - S3/SSH only  
**Impact**: Low - Niche use case

**Current State**:
- AWS S3 support
- SSH/SFTP support
- Basic WebDAV support

**Needed**:
- Google Cloud Storage
- Azure Blob Storage
- Dropbox
- OneDrive/SharePoint

### Connection Management
**Status**: Basic implementation  
**Impact**: Low - UX improvement

**Current State**:
- Connection per operation
- No connection pooling
- Limited error recovery

**Needed**:
- Connection pooling for SSH
- Retry logic with exponential backoff
- Progress reporting for large transfers
- Parallel transfers

---

## Advanced Features (Not Started)

### Watch Mode
**Status**: Not implemented  
**Impact**: Low - Advanced workflow

**Description**: Continuously monitor directories for changes and update diff in real-time.

### Semantic Comparison
**Status**: Not implemented  
**Impact**: Low - Future/experimental

**Description**:
- Refactoring detection (renamed variables/functions)
- AST-based comparison (ignore formatting)
- LLM-powered semantic similarity

### API Server
**Status**: Not implemented  
**Impact**: Low - Enterprise feature

**Description**: Remote comparison service with REST/gRPC API for microservice architectures.

### Platform Integrations
**Status**: Not implemented  
**Impact**: Low - Per-platform

**Examples**:
- macOS: Finder extension, Spotlight, AppleScript
- Windows: Explorer context menu, PowerShell cmdlets
- Linux: Nautilus/Dolphin plugins, DBus service

---

## Testing

### Coverage Gaps
**Status**: Partial coverage  
**Areas needing improvement**:
- Property-based testing (no proptest yet)
- Fuzz testing for parsers (patch, CSV, etc.)
- Multi-platform CI (Linux only currently)
- GUI automated testing
- Performance regression tests in CI

### Benchmark Coverage
**Status**: Basic benchmarks only  
**Needed**:
- Large-scale benchmarks (1M+ files)
- Network filesystem scenarios
- Archive comparison benchmarks
- Historical trend tracking in CI

---

## Documentation

### User Guide
**Status**: README only  
**Needed**:
- Step-by-step tutorial
- Architecture deep-dive
- Plugin development guide (future)
- Video tutorials

### API Reference
**Status**: Inline docs only  
**Needed**:
- Generated API docs website (docs.rs)
- FFI API reference with examples
- Best practices guide

---

## Notes

Many items in this document are **intentional** low-priority features or future enhancements. This list helps:
- Set realistic expectations
- Guide contributor priorities
- Track long-term vision
- Document design decisions

Not everything needs to be implemented - focus areas are determined by:
1. User feedback and requests
2. Performance bottlenecks
3. Critical missing functionality
4. Community contributions

For implementation priorities, see [ROADMAP.md](ROADMAP.md).
