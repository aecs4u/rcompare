# RCompare VFS & Archive Features Roadmap

## Current State (v1.0)

### Implemented VFS Backends

| Backend | Read | Write | Status |
|---------|------|-------|--------|
| **Local Filesystem** | ✅ | ✅ | Full support |
| **ZIP Archives** | ✅ | ❌ | Read-only |
| **TAR/TAR.GZ/TGZ** | ✅ | ❌ | Read-only |
| **7Z Archives** | ✅ | ❌ | Read-only |
| **SFTP** | ✅ | ✅ | Full support via ssh2 |

### VFS Trait Interface

```rust
pub trait Vfs: Send + Sync {
    fn instance_id(&self) -> &str;
    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError>;
    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError>;
    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError>;
    fn remove_file(&self, path: &Path) -> Result<(), VfsError>;
    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError>;
    fn exists(&self, path: &Path) -> bool;
}
```

---

## Phase 1: Archive Write Support (v1.1)

### Priority: HIGH | Effort: MEDIUM

Enable write operations for existing archive formats.

### 1.1 ZIP Write Support

**Crate**: Continue using `zip` crate (supports write)

**Implementation Steps**:
1. Add `create_file()` method to VFS trait
2. Add `remove_file()` implementation for ZIP
3. Implement atomic write (write to temp, then replace)
4. Handle compression level options

**New VFS Trait Methods**:
```rust
/// Creates a new file and returns a Write trait object
fn create_file(&self, path: &Path) -> Result<Box<dyn Write + Send>, VfsError>;

/// Creates a directory
fn create_dir(&self, path: &Path) -> Result<(), VfsError>;

/// Renames/moves a file or directory
fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError>;
```

**Files to Modify**:
- `rcompare_common/src/vfs.rs` - Add write methods to trait
- `rcompare_core/src/vfs/archive.rs` - Implement ZIP write
- `rcompare_core/src/vfs/local.rs` - Implement new methods

### 1.2 TAR Write Support

**Crate**: Continue using `tar` crate (supports write)

**Implementation Steps**:
1. Create `TarWriter` struct for building archives
2. Handle compression (gzip via `flate2`)
3. Preserve file permissions and timestamps
4. Implement streaming write for large files

**Challenges**:
- TAR archives are typically written sequentially
- May need to rebuild entire archive for modifications
- Consider "append mode" for adding files

### 1.3 7Z Write Support

**Crate**: `sevenz-rust` has limited write support

**Implementation Steps**:
1. Evaluate `sevenz-rust` write capabilities
2. If insufficient, consider `lzma-rs` for LZMA compression
3. May need to shell out to `7z` binary as fallback

**Alternative**: Use `compress-tools` crate which wraps `libarchive`

---

## Phase 2: Additional Archive Formats (v1.2)

### Priority: MEDIUM | Effort: MEDIUM

### 2.1 RAR Support (Read-Only)

**Crate**: `unrar` (wrapper around unrar library)

**Implementation Steps**:
1. Add `unrar` dependency
2. Create `RarVfs` struct implementing `Vfs` trait
3. Handle password-protected archives
4. Map RAR-specific errors to `VfsError`

**Code Structure**:
```rust
// rcompare_core/src/vfs/rar.rs
pub struct RarVfs {
    archive_path: PathBuf,
    password: Option<String>,
    entries: Vec<RarEntry>,
}

impl Vfs for RarVfs {
    // Read-only implementation
}
```

**Cargo.toml Addition**:
```toml
[dependencies]
unrar = "0.5"
```

### 2.2 ISO Support (Read-Only)

**Crate**: `cdfs` or `iso9660`

**Use Cases**:
- Compare ISO images
- Extract files from disk images

**Implementation Steps**:
1. Add ISO parsing crate
2. Create `IsoVfs` struct
3. Handle Rock Ridge and Joliet extensions

### 2.3 Compressed Single Files

Support comparing compressed single files:
- `.gz` (gzip)
- `.bz2` (bzip2)
- `.xz` (LZMA)
- `.zst` (Zstandard)

**Crates**:
- `flate2` (gzip)
- `bzip2`
- `xz2` or `liblzma`
- `zstd`

**Implementation**:
```rust
pub struct CompressedFileVfs {
    inner_path: PathBuf,
    compression: CompressionType,
}

pub enum CompressionType {
    Gzip,
    Bzip2,
    Xz,
    Zstd,
}
```

---

## Phase 3: Virtual Folders (v1.3)

### Priority: MEDIUM | Effort: HIGH

### 3.1 Search Results VFS

Create virtual folder from search/filter results.

**Use Cases**:
- Compare only files matching a pattern
- Create filtered view of large directories
- Save search results as comparison source

**Implementation**:
```rust
pub struct FilteredVfs {
    inner: Box<dyn Vfs>,
    filter: FilterPredicate,
    cached_entries: Vec<FileEntry>,
}

pub enum FilterPredicate {
    Glob(String),
    Regex(regex::Regex),
    Size { min: Option<u64>, max: Option<u64> },
    Modified { after: Option<SystemTime>, before: Option<SystemTime> },
    Combined(Vec<FilterPredicate>),
}
```

### 3.2 Union/Overlay VFS

Combine multiple VFS sources into one virtual view.

**Use Cases**:
- Compare merged directory trees
- Overlay patches on base directories
- View multiple archives as one

**Implementation**:
```rust
pub struct UnionVfs {
    layers: Vec<Box<dyn Vfs>>,
    mode: UnionMode,
}

pub enum UnionMode {
    /// First layer wins on conflict
    FirstWins,
    /// Last layer wins on conflict
    LastWins,
    /// Show all as separate entries
    ShowAll,
}
```

### 3.3 Snapshot VFS

Create point-in-time snapshot for comparison.

**Use Cases**:
- Compare current state vs. saved snapshot
- Track changes over time
- Undo/rollback support

**Implementation**:
```rust
pub struct SnapshotVfs {
    snapshot_path: PathBuf,  // Serialized FileEntry list
    metadata_cache: HashMap<PathBuf, FileMetadata>,
}
```

---

## Phase 4: Cloud & Network VFS (v2.0)

### Priority: LOW | Effort: HIGH

### 4.1 WebDAV Support

**Crate**: `webdav-client` or `reqwest` with WebDAV protocol

**Use Cases**:
- Nextcloud/ownCloud servers
- Corporate file shares
- Online storage services

### 4.2 S3-Compatible Storage

**Crate**: `aws-sdk-s3` or `rusoto_s3`

**Use Cases**:
- AWS S3 buckets
- MinIO servers
- Backblaze B2
- Google Cloud Storage (S3-compatible mode)

**Implementation Considerations**:
- Pagination for large buckets
- Parallel listing with prefixes
- Caching for performance
- Credential management

### 4.3 Google Drive / OneDrive

**Complexity**: HIGH (OAuth, API rate limits)

**Recommendation**: Defer to dedicated sync tools or use FUSE mounts

---

## Phase 5: Version Control VFS (Future)

### Priority: LOW | Effort: VERY HIGH

### 5.1 Git Repository VFS

**Crate**: `git2` (libgit2 bindings)

**Features**:
- Compare branches/commits
- View file at specific revision
- Browse history

**Implementation**:
```rust
pub struct GitVfs {
    repo: git2::Repository,
    reference: GitRef,
}

pub enum GitRef {
    Head,
    Branch(String),
    Commit(git2::Oid),
    Tag(String),
}
```

### 5.2 SVN Support

**Complexity**: HIGH (SVN protocol, authentication)

**Recommendation**: Lower priority, Git dominates modern VCS usage

---

## Implementation Priority Matrix

| Feature | Impact | Effort | Priority | Target |
|---------|--------|--------|----------|--------|
| ZIP Write | High | Medium | P1 | v1.1 |
| TAR Write | High | Medium | P1 | v1.1 |
| RAR Read | Medium | Low | P2 | v1.2 |
| 7Z Write | Medium | High | P3 | v1.2 |
| ISO Read | Low | Medium | P3 | v1.2 |
| Compressed Files | Medium | Low | P2 | v1.2 |
| Search Results VFS | High | Medium | P2 | v1.3 |
| Union VFS | Medium | Medium | P3 | v1.3 |
| Snapshot VFS | Medium | Medium | P3 | v1.3 |
| WebDAV | Low | High | P4 | v2.0 |
| S3 | Low | High | P4 | v2.0 |
| Git VFS | Medium | Very High | P5 | v2.x |

---

## Technical Considerations

### Extended VFS Trait

For full write support, extend the trait:

```rust
pub trait VfsWrite: Vfs {
    /// Check if VFS supports write operations
    fn is_writable(&self) -> bool;

    /// Create a new file
    fn create_file(&self, path: &Path) -> Result<Box<dyn Write + Send>, VfsError>;

    /// Create a directory
    fn create_dir(&self, path: &Path) -> Result<(), VfsError>;

    /// Create directory and all parents
    fn create_dir_all(&self, path: &Path) -> Result<(), VfsError>;

    /// Rename/move a file or directory
    fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError>;

    /// Set file modification time
    fn set_mtime(&self, path: &Path, mtime: SystemTime) -> Result<(), VfsError>;

    /// Flush any pending writes
    fn flush(&self) -> Result<(), VfsError>;
}
```

### Transaction Support

For archive writes, implement transactional semantics:

```rust
pub trait VfsTransaction: VfsWrite {
    /// Begin a transaction
    fn begin(&self) -> Result<TransactionId, VfsError>;

    /// Commit changes
    fn commit(&self, tx: TransactionId) -> Result<(), VfsError>;

    /// Rollback changes
    fn rollback(&self, tx: TransactionId) -> Result<(), VfsError>;
}
```

### Async VFS (Future)

For network VFS backends, consider async interface:

```rust
#[async_trait]
pub trait AsyncVfs: Send + Sync {
    async fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError>;
    async fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError>;
    async fn open_file(&self, path: &Path) -> Result<AsyncRead, VfsError>;
}
```

---

## Testing Strategy

### Unit Tests

Each VFS backend needs:
- Basic read operations
- Directory listing
- Error handling
- Edge cases (empty files, deep paths, special characters)

### Integration Tests

- Cross-VFS copy operations
- Archive round-trip (create, modify, verify)
- Large file handling
- Concurrent access

### Test Fixtures

Create test archives for each format:
```
tests/fixtures/
├── test.zip
├── test.tar.gz
├── test.7z
├── test.rar
└── test.iso
```

---

## Dependencies Summary

### Current
- `zip` - ZIP archives
- `tar` - TAR archives
- `flate2` - gzip compression
- `sevenz-rust` - 7Z archives
- `ssh2` - SFTP

### Phase 1-2 Additions
- `unrar` - RAR archives (read-only)
- `cdfs` or `iso9660` - ISO images
- `bzip2` - bzip2 compression
- `xz2` - LZMA compression
- `zstd` - Zstandard compression

### Phase 4 Additions (Optional)
- `aws-sdk-s3` - S3 storage
- `reqwest` - HTTP/WebDAV
- `git2` - Git repositories

---

## Milestones

### v1.1 (Archive Write)
- [ ] Extend VFS trait with write methods
- [ ] Implement ZIP write support
- [ ] Implement TAR write support
- [ ] Add sync operations for archives
- [ ] GUI integration for archive modifications

### v1.2 (More Formats)
- [ ] RAR read support
- [ ] ISO read support
- [ ] Compressed file support (.gz, .bz2, .xz, .zst)
- [ ] 7Z write support (if feasible)

### v1.3 (Virtual Folders)
- [ ] Search Results VFS
- [ ] Union/Overlay VFS
- [ ] Snapshot VFS
- [ ] GUI integration for virtual folders

### v2.0 (Cloud/Network)
- [ ] WebDAV support
- [ ] S3-compatible storage
- [ ] Improved caching and offline support

---

## Conclusion

This roadmap prioritizes features that provide the most value with reasonable implementation effort. Archive write support (Phase 1) is the highest priority as it enables bidirectional sync operations with archives. Additional archive formats (Phase 2) expand compatibility. Virtual folders (Phase 3) provide advanced filtering and comparison capabilities. Cloud/network support (Phase 4+) is lower priority due to complexity and the availability of alternative tools (rclone, FUSE mounts).
