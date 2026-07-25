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
//! - **Full and partial hashes**: Supports both complete file hashing and partial (8KB)
//! - **Binary serialization**: Uses bincode for efficient disk storage
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
use std::fs;
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
    /// Set whenever a new entry is recorded; `persist()` skips the disk
    /// write entirely when this is still `false`, avoiding a pointless
    /// serialize-and-rewrite of an unchanged (or read-only/disabled) cache.
    dirty: AtomicBool,
}

impl HashCache {
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
            dirty: AtomicBool::new(false),
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

        Ok(Self {
            cache_dir,
            mode,
            memory_cache: Arc::new(RwLock::new(memory_cache)),
            dirty: AtomicBool::new(false),
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
            cache.insert(key, hash);
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

        let cache_file = self.cache_dir.join("hash_cache.bin");
        let temp_file = self.cache_dir.join("hash_cache.bin.tmp");

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
            debug!("Pruned {} stale cache entries (file no longer exists)", pruned);
        }

        let data =
            bincode::serialize(&*cache).map_err(|e| RCompareError::Serialization(e.to_string()))?;

        // Write to temporary file first
        fs::write(&temp_file, data)?;

        // Atomically rename temporary file to final cache file
        // This ensures the cache file is never corrupted even if the process crashes
        fs::rename(&temp_file, &cache_file)?;

        debug!("Persisted {} cache entries to disk (atomic)", cache.len());
        self.dirty.store(false, Ordering::Relaxed);

        Ok(())
    }

    /// Clear all cache entries
    pub fn clear(&self) {
        if let Ok(mut cache) = self.memory_cache.write() {
            cache.clear();
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
