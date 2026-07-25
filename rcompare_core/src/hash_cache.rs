//! Persistent BLAKE3 hash cache with in-memory and disk storage.
//!
//! This module provides a thread-safe hash cache that stores BLAKE3 file hashes
//! both in memory and on disk, enabling efficient repeated comparisons of large
//! file trees. The cache uses file size and modification time as cache keys,
//! automatically invalidating entries when files change.
//!
//! # Features
//!
//! - **Persistent storage**: Hashes survive across program runs
//! - **Thread-safe**: Uses RwLock for concurrent access
//! - **Automatic invalidation**: Cache entries include size/mtime for validation
//! - **Incremental persistence**: Appends only changed entries between compactions
//! - **Binary serialization**: Uses bincode snapshots and journal records
//!
//! # Cache Key Strategy
//!
//! Cache entries are keyed by:
//! - File path (relative to scan root)
//! - File size
//! - Modification timestamp
//!
//! This ensures that cached hashes are automatically invalidated when files
//! are modified, preventing stale data.
//!
//! # Examples
//!
//! Basic usage:
//!
//! ```no_run
//! use rcompare_core::hash_cache::HashCache;
//! use rcompare_common::CacheKey;
//! use std::path::{Path, PathBuf};
//! use std::time::SystemTime;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
//!
//! let key = CacheKey {
//!     path: PathBuf::from("file.txt"),
//!     size: 1024,
//!     modified: SystemTime::now(),
//! };
//!
//! // Check if hash is cached
//! if let Some(hash) = cache.get(&key) {
//!     println!("Cached hash found: {}", hash.to_hex());
//! } else {
//!     // Compute and cache the hash
//!     // cache.insert(key, computed_hash);
//! }
//!
//! // Persist cache to disk
//! cache.persist()?;
//! # Ok(())
//! # }
//! ```

use rcompare_common::{Blake3Hash, CacheKey, RCompareError};
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};
use tracing::{debug, warn};

/// Controls how a [`HashCache`] reads and writes its backing store.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CacheMode {
    /// Read existing entries and record new ones (default).
    ReadWrite,
    /// Read existing entries but never add new ones or write to disk.
    /// Useful for CI or read-only filesystems where cache growth isn't wanted.
    ReadOnly,
    /// Don't read or write anything; every lookup misses. Equivalent to
    /// running without a cache at all.
    Disabled,
}

/// Thread-safe in-memory and disk-backed BLAKE3 hash cache.
///
/// The cache stores file hashes keyed by path, size, and modification time,
/// enabling efficient detection of file changes across multiple comparison runs.
/// Cache data is automatically loaded from disk on creation and can be persisted
/// back to disk using [`persist()`](HashCache::persist).
///
/// # Thread Safety
///
/// The cache uses `RwLock` to allow multiple concurrent readers or a single writer,
/// making it safe to use from multiple threads during parallel directory scans.
///
/// # Examples
///
/// ```no_run
/// use rcompare_core::hash_cache::HashCache;
/// use std::path::Path;
///
/// # fn main() -> Result<(), Box<dyn std::error::Error>> {
/// let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
/// // Use cache for comparisons...
/// cache.persist()?; // Save to disk
/// # Ok(())
/// # }
/// ```
pub struct HashCache {
    cache_dir: PathBuf,
    mode: CacheMode,
    memory_cache: Arc<RwLock<HashMap<CacheKey, Blake3Hash>>>,
    /// Entries not yet appended to the incremental journal.
    pending: Arc<RwLock<HashMap<CacheKey, Blake3Hash>>>,
    /// Set whenever a new entry is recorded; `persist()` skips the disk
    /// write entirely when this is still `false`, avoiding a pointless
    /// serialize-and-rewrite of an unchanged (or read-only/disabled) cache.
    dirty: AtomicBool,
    /// Set by operations (such as pruning/clear) that cannot be represented
    /// by an append-only update and therefore require a snapshot compaction.
    compact: AtomicBool,
}

impl HashCache {
    const JOURNAL_COMPACT_BYTES: u64 = 8 * 1024 * 1024;

    pub fn new(cache_dir: PathBuf) -> Result<Self, RCompareError> {
        Self::with_mode(cache_dir, CacheMode::ReadWrite)
    }

    /// Create a cache that never reads or writes anything (`--no-cache`).
    /// Every lookup misses and hashes are recomputed every time.
    pub fn disabled() -> Self {
        Self {
            cache_dir: PathBuf::new(),
            mode: CacheMode::Disabled,
            memory_cache: Arc::new(RwLock::new(HashMap::new())),
            pending: Arc::new(RwLock::new(HashMap::new())),
            dirty: AtomicBool::new(false),
            compact: AtomicBool::new(false),
        }
    }

    /// Create a cache in the given mode. `ReadWrite`/`ReadOnly` both load
    /// existing entries from `cache_dir`; `Disabled` ignores `cache_dir`
    /// entirely (use [`HashCache::disabled`] if you don't have a directory
    /// to pass at all).
    pub fn with_mode(cache_dir: PathBuf, mode: CacheMode) -> Result<Self, RCompareError> {
        if mode == CacheMode::Disabled {
            return Ok(Self::disabled());
        }

        if !cache_dir.exists() {
            fs::create_dir_all(&cache_dir)?;
        }

        let mut memory_cache = HashMap::new();

        // Load existing cache from disk
        let cache_file = cache_dir.join("hash_cache.bin");
        if cache_file.exists() {
            match fs::read(&cache_file) {
                Ok(data) => {
                    if let Ok(cached_data) =
                        bincode::deserialize::<HashMap<CacheKey, Blake3Hash>>(&data)
                    {
                        memory_cache = cached_data;
                        debug!("Loaded {} entries from cache", memory_cache.len());
                    }
                }
                Err(e) => {
                    warn!("Failed to load cache file: {}", e);
                }
            }
        }

        // New writes use an append-only journal so a scan only serializes its
        // changed entries. A truncated final record (for example after power
        // loss) is ignored; earlier complete records remain usable.
        let journal_file = cache_dir.join("hash_cache.journal");
        let mut journal_needs_compaction = false;
        if journal_file.exists() {
            match fs::File::open(&journal_file) {
                Ok(mut file) => loop {
                    let mut length = [0_u8; 8];
                    match file.read(&mut length[..1]) {
                        Ok(0) => break,
                        Ok(1) => {}
                        Ok(_) => unreachable!("one-byte read returned more than one byte"),
                        Err(e) => {
                            warn!("Failed to read cache journal: {}", e);
                            journal_needs_compaction = true;
                            break;
                        }
                    }
                    if file.read_exact(&mut length[1..]).is_err() {
                        warn!("Ignoring truncated cache journal length");
                        journal_needs_compaction = true;
                        break;
                    }
                    let record_len = u64::from_le_bytes(length);
                    let Ok(record_len) = usize::try_from(record_len) else {
                        warn!("Ignoring oversized cache journal record");
                        journal_needs_compaction = true;
                        break;
                    };
                    if record_len > Self::JOURNAL_COMPACT_BYTES as usize {
                        warn!("Ignoring oversized cache journal record");
                        journal_needs_compaction = true;
                        break;
                    }
                    let mut record = vec![0_u8; record_len];
                    if file.read_exact(&mut record).is_err() {
                        warn!("Ignoring truncated cache journal record");
                        journal_needs_compaction = true;
                        break;
                    }
                    match bincode::deserialize::<Vec<(CacheKey, Blake3Hash)>>(&record) {
                        Ok(entries) => memory_cache.extend(entries),
                        Err(e) => {
                            warn!("Ignoring invalid cache journal record: {}", e);
                            journal_needs_compaction = true;
                            break;
                        }
                    }
                },
                Err(e) => warn!("Failed to open cache journal: {}", e),
            }
        }

        Ok(Self {
            cache_dir,
            mode,
            memory_cache: Arc::new(RwLock::new(memory_cache)),
            pending: Arc::new(RwLock::new(HashMap::new())),
            dirty: AtomicBool::new(false),
            compact: AtomicBool::new(journal_needs_compaction),
        })
    }

    /// Get cached hash for a file
    pub fn get(&self, key: &CacheKey) -> Option<Blake3Hash> {
        if self.mode == CacheMode::Disabled {
            return None;
        }
        self.memory_cache.read().ok()?.get(key).copied()
    }

    /// Store hash in cache. No-op in `ReadOnly`/`Disabled` mode.
    pub fn put(&self, key: CacheKey, hash: Blake3Hash) {
        if self.mode != CacheMode::ReadWrite {
            return;
        }
        if let Ok(mut cache) = self.memory_cache.write() {
            cache.insert(key.clone(), hash);
            if let Ok(mut pending) = self.pending.write() {
                pending.insert(key, hash);
            }
            self.dirty.store(true, Ordering::Relaxed);
        }
    }

    /// Persist cache to disk atomically. Skipped entirely when the cache is
    /// read-only/disabled, or when nothing new was recorded since the last
    /// load/persist (the common case for a scan whose files were all cache
    /// hits).
    pub fn persist(&self) -> Result<(), RCompareError> {
        if self.mode != CacheMode::ReadWrite {
            return Ok(());
        }
        if !self.dirty.load(Ordering::Relaxed) {
            debug!("Cache unchanged; skipping persist");
            return Ok(());
        }

        let mut cache = self
            .memory_cache
            .write()
            .map_err(|e| RCompareError::Cache(format!("Lock error: {e}")))?;

        // Prune entries for files that no longer exist: they can never be
        // looked up again (the cache key includes the path) and just bloat
        // the on-disk map over time.
        let before = cache.len();
        cache.retain(|key, _| key.path.exists());
        let pruned = before - cache.len();
        if pruned > 0 {
            debug!(
                "Pruned {} stale cache entries (file no longer exists)",
                pruned
            );
            self.compact.store(true, Ordering::Relaxed);
        }

        let cache_file = self.cache_dir.join("hash_cache.bin");
        let journal_file = self.cache_dir.join("hash_cache.journal");
        let journal_too_large = journal_file
            .metadata()
            .map(|meta| meta.len() >= Self::JOURNAL_COMPACT_BYTES)
            .unwrap_or(false);

        if self.compact.load(Ordering::Relaxed) || journal_too_large {
            let temp_file = self.cache_dir.join("hash_cache.bin.tmp");
            let data = bincode::serialize(&*cache)
                .map_err(|e| RCompareError::Serialization(e.to_string()))?;
            fs::write(&temp_file, data)?;
            fs::rename(&temp_file, &cache_file)?;
            if journal_file.exists() {
                fs::remove_file(&journal_file)?;
            }
            self.pending
                .write()
                .map_err(|e| RCompareError::Cache(format!("Lock error: {e}")))?
                .clear();
            self.compact.store(false, Ordering::Relaxed);
            debug!("Compacted {} cache entries to disk", cache.len());
        } else {
            let mut pending = self
                .pending
                .write()
                .map_err(|e| RCompareError::Cache(format!("Lock error: {e}")))?;
            let entries: Vec<_> = pending
                .iter()
                .map(|(key, hash)| (key.clone(), *hash))
                .collect();
            if !entries.is_empty() {
                let data = bincode::serialize(&entries)
                    .map_err(|e| RCompareError::Serialization(e.to_string()))?;
                let mut journal = OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&journal_file)?;
                journal.write_all(&(data.len() as u64).to_le_bytes())?;
                journal.write_all(&data)?;
                journal.sync_data()?;
                pending.clear();
                debug!("Appended {} changed cache entries", entries.len());
            }
        }

        self.dirty.store(false, Ordering::Relaxed);

        Ok(())
    }

    /// Clear all cache entries
    pub fn clear(&self) {
        if let Ok(mut cache) = self.memory_cache.write() {
            cache.clear();
            if let Ok(mut pending) = self.pending.write() {
                pending.clear();
            }
            self.compact.store(true, Ordering::Relaxed);
            self.dirty.store(true, Ordering::Relaxed);
        }
    }

    /// Get the number of cached entries
    pub fn len(&self) -> usize {
        self.memory_cache.read().map(|c| c.len()).unwrap_or(0)
    }

    /// Check if cache is empty
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::SystemTime;
    use tempfile::TempDir;

    #[test]
    fn test_hash_cache_basic() {
        let temp = TempDir::new().unwrap();
        let cache = HashCache::new(temp.path().to_path_buf()).unwrap();

        let key = CacheKey {
            path: PathBuf::from("test.txt"),
            modified: SystemTime::now(),
            size: 100,
        };
        let hash = Blake3Hash([1; 32]);

        assert!(cache.get(&key).is_none());

        cache.put(key.clone(), hash);
        assert_eq!(cache.get(&key), Some(hash));
        assert_eq!(cache.len(), 1);
    }

    #[test]
    fn test_hash_cache_persistence() {
        let temp = TempDir::new().unwrap();
        // persist() prunes entries whose file no longer exists, so the
        // cached path must be real for it to survive a reload.
        let file_path = temp.path().join("test.txt");
        std::fs::write(&file_path, b"hello").unwrap();

        let key = CacheKey {
            path: file_path,
            modified: SystemTime::now(),
            size: 100,
        };
        let hash = Blake3Hash([2; 32]);

        let cache_dir = temp.path().join("cache");
        {
            let cache = HashCache::new(cache_dir.clone()).unwrap();
            cache.put(key.clone(), hash);
            cache.persist().unwrap();
        }

        {
            let cache = HashCache::new(cache_dir).unwrap();
            assert_eq!(cache.get(&key), Some(hash));
        }
    }

    #[test]
    fn test_hash_cache_persists_incremental_journal_records() {
        let temp = TempDir::new().unwrap();
        let cache_dir = temp.path().join("cache");
        let first_path = temp.path().join("first.txt");
        let second_path = temp.path().join("second.txt");
        std::fs::write(&first_path, b"first").unwrap();
        std::fs::write(&second_path, b"second").unwrap();
        let first_key = CacheKey {
            path: first_path,
            modified: SystemTime::now(),
            size: 5,
        };
        let second_key = CacheKey {
            path: second_path,
            modified: SystemTime::now(),
            size: 6,
        };

        let cache = HashCache::new(cache_dir.clone()).unwrap();
        cache.put(first_key.clone(), Blake3Hash([7; 32]));
        cache.persist().unwrap();
        let journal = cache_dir.join("hash_cache.journal");
        let first_len = journal.metadata().unwrap().len();

        cache.put(second_key.clone(), Blake3Hash([8; 32]));
        cache.persist().unwrap();
        assert!(journal.metadata().unwrap().len() > first_len);
        assert!(!cache_dir.join("hash_cache.bin").exists());
        drop(cache);

        let reloaded = HashCache::new(cache_dir).unwrap();
        assert_eq!(reloaded.get(&first_key), Some(Blake3Hash([7; 32])));
        assert_eq!(reloaded.get(&second_key), Some(Blake3Hash([8; 32])));
    }

    #[test]
    fn test_hash_cache_persist_prunes_missing_files() {
        let temp = TempDir::new().unwrap();
        let missing_path = temp.path().join("gone.txt"); // never created

        let key = CacheKey {
            path: missing_path,
            modified: SystemTime::now(),
            size: 100,
        };
        let cache_dir = temp.path().join("cache");
        let cache = HashCache::new(cache_dir).unwrap();
        cache.put(key.clone(), Blake3Hash([3; 32]));
        assert_eq!(cache.len(), 1);

        cache.persist().unwrap();
        // Pruned in-memory too (persist() prunes the live map, not a copy)...
        assert_eq!(cache.len(), 0);

        // ...and absent from what actually got written to disk.
        drop(cache);
        let cache = HashCache::new(temp.path().join("cache")).unwrap();
        assert!(cache.get(&key).is_none());
        assert_eq!(cache.len(), 0);
    }

    #[test]
    fn test_hash_cache_persist_skips_write_when_not_dirty() {
        let temp = TempDir::new().unwrap();
        let cache = HashCache::new(temp.path().to_path_buf()).unwrap();
        // Never called put(), so the cache is clean; persist() should not
        // even create the cache file.
        cache.persist().unwrap();
        assert!(!temp.path().join("hash_cache.bin").exists());
    }

    #[test]
    fn test_hash_cache_disabled_mode_never_caches() {
        let cache = HashCache::disabled();
        let key = CacheKey {
            path: PathBuf::from("/nonexistent/anything.txt"),
            modified: SystemTime::now(),
            size: 42,
        };
        cache.put(key.clone(), Blake3Hash([4; 32]));
        assert!(cache.get(&key).is_none());
        assert_eq!(cache.len(), 0);
    }

    #[test]
    fn test_hash_cache_read_only_mode_reads_but_does_not_write() {
        let temp = TempDir::new().unwrap();
        let file_path = temp.path().join("test.txt");
        std::fs::write(&file_path, b"hello").unwrap();
        let key = CacheKey {
            path: file_path,
            modified: SystemTime::now(),
            size: 100,
        };
        let cache_dir = temp.path().join("cache");

        // Seed the cache in read-write mode first.
        {
            let cache = HashCache::with_mode(cache_dir.clone(), CacheMode::ReadWrite).unwrap();
            cache.put(key.clone(), Blake3Hash([5; 32]));
            cache.persist().unwrap();
        }

        // Read-only: existing entry is visible, new entries are dropped,
        // and persist() doesn't touch disk.
        let cache = HashCache::with_mode(cache_dir, CacheMode::ReadOnly).unwrap();
        assert_eq!(cache.get(&key), Some(Blake3Hash([5; 32])));

        let other_key = CacheKey {
            path: PathBuf::from("/other/file.txt"),
            modified: SystemTime::now(),
            size: 7,
        };
        cache.put(other_key.clone(), Blake3Hash([6; 32]));
        assert!(cache.get(&other_key).is_none());
        cache.persist().unwrap(); // no-op, must not error
    }
}
