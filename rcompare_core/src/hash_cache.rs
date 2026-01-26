use rcompare_common::{Blake3Hash, CacheKey, RCompareError};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, RwLock};
use tracing::{debug, warn};

/// In-memory and disk-backed hash cache
pub struct HashCache {
    cache_dir: PathBuf,
    memory_cache: Arc<RwLock<HashMap<CacheKey, Blake3Hash>>>,
}

impl HashCache {
    pub fn new(cache_dir: PathBuf) -> Result<Self, RCompareError> {
        if !cache_dir.exists() {
            fs::create_dir_all(&cache_dir)?;
        }

        let mut memory_cache = HashMap::new();

        // Load existing cache from disk
        let cache_file = cache_dir.join("hash_cache.bin");
        if cache_file.exists() {
            match fs::read(&cache_file) {
                Ok(data) => {
                    if let Ok(cached_data) = bincode::deserialize::<HashMap<CacheKey, Blake3Hash>>(&data) {
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
            memory_cache: Arc::new(RwLock::new(memory_cache)),
        })
    }

    /// Get cached hash for a file
    pub fn get(&self, key: &CacheKey) -> Option<Blake3Hash> {
        self.memory_cache.read().ok()?.get(key).copied()
    }

    /// Store hash in cache
    pub fn put(&self, key: CacheKey, hash: Blake3Hash) {
        if let Ok(mut cache) = self.memory_cache.write() {
            cache.insert(key, hash);
        }
    }

    /// Persist cache to disk atomically
    pub fn persist(&self) -> Result<(), RCompareError> {
        let cache_file = self.cache_dir.join("hash_cache.bin");
        let temp_file = self.cache_dir.join("hash_cache.bin.tmp");

        let cache = self.memory_cache.read()
            .map_err(|e| RCompareError::Cache(format!("Lock error: {}", e)))?;

        let data = bincode::serialize(&*cache)
            .map_err(|e| RCompareError::Serialization(e.to_string()))?;

        // Write to temporary file first
        fs::write(&temp_file, data)?;

        // Atomically rename temporary file to final cache file
        // This ensures the cache file is never corrupted even if the process crashes
        fs::rename(&temp_file, &cache_file)?;

        debug!("Persisted {} cache entries to disk (atomic)", cache.len());

        Ok(())
    }

    /// Clear all cache entries
    pub fn clear(&self) {
        if let Ok(mut cache) = self.memory_cache.write() {
            cache.clear();
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

        let key = CacheKey {
            path: PathBuf::from("test.txt"),
            modified: SystemTime::now(),
            size: 100,
        };
        let hash = Blake3Hash([2; 32]);

        {
            let cache = HashCache::new(temp.path().to_path_buf()).unwrap();
            cache.put(key.clone(), hash);
            cache.persist().unwrap();
        }

        {
            let cache = HashCache::new(temp.path().to_path_buf()).unwrap();
            assert_eq!(cache.get(&key), Some(hash));
        }
    }
}
