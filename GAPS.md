# Known Gaps and Limitations

This document tracks known limitations, gaps, and areas for improvement in RCompare.

Last updated: 2026-01-30

---

## Performance

### 🚧 Parallel Hash Computing (In Progress)
**Status**: Implementation planned for Phase 4  
**Impact**: High - 2-3x performance improvement expected

**Current State**:
- BLAKE3 hashing is single-threaded
- Sequential file processing
- ~3GB/s throughput on modern CPUs

**Planned Improvement**:
- Multi-threaded hash computing with rayon
- Work-stealing queue for load balancing
- Configurable thread pool size
- Target: 6-9GB/s on 4-8 core systems

### Streaming Large Files
**Status**: Not implemented  
**Impact**: Medium - Important for 1GB+ files

**Current State**:
- Files loaded entirely into memory for comparison
- Memory usage scales with file size
- May cause OOM for very large files

**Planned Solution**:
- Chunked reading and comparison
- Streaming hash computation
- Progress reporting for long operations

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

### Exit Codes
**Status**: Limited implementation  
**Impact**: Low - CI integration use case

**Current State**:
- Exit 0 on success
- Exit 1 on error
- No exit code based on diff presence

**Needed**:
- Exit 0: No differences found
- Exit 1: Differences found
- Exit 2: Error occurred
- Configurable behavior via flag

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

### Three-Way Merge
**Status**: Not implemented  
**Impact**: High - Advanced workflow

**Description**: Compare base, left, and right versions for merge conflict resolution.

**Implementation**:
- Core merge engine in rcompare_core
- Three-pane GUI layout
- Conflict detection and resolution UI
- Auto-merge non-conflicting changes

---

## Copy Operations

### Post-Copy Verification
**Status**: Not implemented  
**Impact**: Medium - Data integrity

**Description**: Verify BLAKE3 hash after copy to detect corruption.

**Implementation**:
- Hash source before copy
- Hash destination after copy
- Compare and report mismatches
- Retry failed copies

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
- CLI text output
- JSON output for automation
- No visual reports

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
