#![allow(clippy::too_many_arguments)]

use crate::hash_cache::HashCache;
use rcompare_common::{
    Blake3Hash, CacheKey, DiffNode, DiffStatus, FileEntry, RCompareError, ThreeWayDiffNode,
    ThreeWayDiffStatus, Vfs,
};
use std::collections::HashMap;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use tracing::{debug, info};

/// Comparison engine for comparing file trees
pub struct ComparisonEngine {
    cache: HashCache,
    verify_hashes: bool,
}

impl ComparisonEngine {
    pub fn new(cache: HashCache) -> Self {
        Self {
            cache,
            verify_hashes: false,
        }
    }

    pub fn with_hash_verification(mut self, enabled: bool) -> Self {
        self.verify_hashes = enabled;
        self
    }

    pub fn persist_cache(&self) -> Result<(), RCompareError> {
        self.cache.persist()
    }

    /// Compare two lists of file entries and produce a diff tree
    pub fn compare(
        &self,
        left_root: &Path,
        right_root: &Path,
        left_entries: Vec<FileEntry>,
        right_entries: Vec<FileEntry>,
    ) -> Result<Vec<DiffNode>, RCompareError> {
        self.compare_with_vfs_and_cancel(
            left_root,
            right_root,
            left_entries,
            right_entries,
            None,
            None,
            None,
        )
    }

    pub fn compare_with_vfs(
        &self,
        left_root: &Path,
        right_root: &Path,
        left_entries: Vec<FileEntry>,
        right_entries: Vec<FileEntry>,
        left_vfs: Option<&dyn Vfs>,
        right_vfs: Option<&dyn Vfs>,
    ) -> Result<Vec<DiffNode>, RCompareError> {
        self.compare_with_vfs_and_cancel(
            left_root,
            right_root,
            left_entries,
            right_entries,
            left_vfs,
            right_vfs,
            None,
        )
    }

    pub fn compare_with_vfs_and_cancel(
        &self,
        left_root: &Path,
        right_root: &Path,
        left_entries: Vec<FileEntry>,
        right_entries: Vec<FileEntry>,
        left_vfs: Option<&dyn Vfs>,
        right_vfs: Option<&dyn Vfs>,
        cancel: Option<&AtomicBool>,
    ) -> Result<Vec<DiffNode>, RCompareError> {
        info!(
            "Comparing {} left entries with {} right entries",
            left_entries.len(),
            right_entries.len()
        );

        let mut left_map: HashMap<PathBuf, FileEntry> = left_entries
            .into_iter()
            .map(|e| (e.path.clone(), e))
            .collect();

        let mut right_map: HashMap<PathBuf, FileEntry> = right_entries
            .into_iter()
            .map(|e| (e.path.clone(), e))
            .collect();

        let mut diff_nodes = Vec::new();

        // Find all unique paths
        let mut all_paths: Vec<PathBuf> =
            left_map.keys().chain(right_map.keys()).cloned().collect();
        all_paths.sort();
        all_paths.dedup();

        for path in all_paths {
            if cancel.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
                return Err(RCompareError::Comparison(
                    "Comparison cancelled".to_string(),
                ));
            }

            let left = left_map.remove(&path);
            let right = right_map.remove(&path);

            let status = match (&left, &right) {
                (Some(l), Some(r)) => {
                    if l.is_dir && r.is_dir {
                        DiffStatus::Same
                    } else if l.is_dir || r.is_dir {
                        DiffStatus::Different
                    } else {
                        self.compare_files(left_root, right_root, left_vfs, right_vfs, l, r)?
                    }
                }
                (Some(_), None) => DiffStatus::OrphanLeft,
                (None, Some(_)) => DiffStatus::OrphanRight,
                (None, None) => continue,
            };

            diff_nodes.push(DiffNode {
                relative_path: path,
                left,
                right,
                status,
            });
        }

        debug!("Generated {} diff nodes", diff_nodes.len());
        Ok(diff_nodes)
    }

    /// Compare two individual files
    fn compare_files(
        &self,
        left_root: &Path,
        right_root: &Path,
        left_vfs: Option<&dyn Vfs>,
        right_vfs: Option<&dyn Vfs>,
        left: &FileEntry,
        right: &FileEntry,
    ) -> Result<DiffStatus, RCompareError> {
        // Safety check: ensure neither entry is a directory
        // (catches cases where is_dir flag might be incorrect due to symlinks)
        if left.is_dir || right.is_dir {
            return Ok(DiffStatus::Different);
        }

        // Quick size check
        if left.size != right.size {
            return Ok(DiffStatus::Different);
        }

        if !self.verify_hashes {
            // If sizes match and timestamps match, assume same
            if left.modified == right.modified {
                return Ok(DiffStatus::Same);
            }

            // Otherwise, we'd need to compare content/hashes
            return Ok(DiffStatus::Unchecked);
        }

        let left_path = left_root.join(&left.path);
        let right_path = right_root.join(&right.path);

        if left_vfs.is_none() && right_vfs.is_none() {
            // Try to hash files, but handle broken symlinks gracefully
            let left_partial = match self.partial_hash_file(&left_path) {
                Ok(hash) => hash,
                Err(RCompareError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                    debug!("Skipping broken symlink: {}", left_path.display());
                    return Ok(DiffStatus::Different);
                }
                Err(e) => return Err(e),
            };

            let right_partial = match self.partial_hash_file(&right_path) {
                Ok(hash) => hash,
                Err(RCompareError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                    debug!("Skipping broken symlink: {}", right_path.display());
                    return Ok(DiffStatus::Different);
                }
                Err(e) => return Err(e),
            };

            if left_partial != right_partial {
                return Ok(DiffStatus::Different);
            }

            let same = match self.verify_files(&left_path, &right_path) {
                Ok(result) => result,
                Err(RCompareError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                    debug!("Skipping broken symlink during verification");
                    return Ok(DiffStatus::Different);
                }
                Err(e) => return Err(e),
            };

            return Ok(if same {
                DiffStatus::Same
            } else {
                DiffStatus::Different
            });
        }

        let left_reader = match self.open_reader(&left_path, left_vfs) {
            Ok(reader) => reader,
            Err(RCompareError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                debug!("Skipping broken symlink: {}", left_path.display());
                return Ok(DiffStatus::Different);
            }
            Err(e) => return Err(e),
        };

        let right_reader = match self.open_reader(&right_path, right_vfs) {
            Ok(reader) => reader,
            Err(RCompareError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                debug!("Skipping broken symlink: {}", right_path.display());
                return Ok(DiffStatus::Different);
            }
            Err(e) => return Err(e),
        };

        let left_hash = self.hash_reader(left_reader)?;
        let right_hash = self.hash_reader(right_reader)?;

        Ok(if left_hash == right_hash {
            DiffStatus::Same
        } else {
            DiffStatus::Different
        })
    }

    /// Compute hash for a file
    pub fn hash_file(&self, path: &Path) -> Result<Blake3Hash, RCompareError> {
        // Check for broken symlinks first (use symlink_metadata which doesn't follow symlinks)
        let symlink_meta = std::fs::symlink_metadata(path).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to read metadata for {}: {}", path.display(), e),
            ))
        })?;

        // If it's a symlink, try to follow it
        if symlink_meta.file_type().is_symlink() {
            // Try to get the real metadata by following the symlink
            match std::fs::metadata(path) {
                Ok(real_meta) if real_meta.is_dir() => {
                    return Err(RCompareError::Io(std::io::Error::new(
                        std::io::ErrorKind::IsADirectory,
                        format!("Cannot hash directory symlink: {}", path.display()),
                    )));
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    return Err(RCompareError::Io(std::io::Error::new(
                        std::io::ErrorKind::NotFound,
                        format!("Broken symlink (target does not exist): {}", path.display()),
                    )));
                }
                Err(e) => {
                    return Err(RCompareError::Io(std::io::Error::new(
                        e.kind(),
                        format!("Failed to follow symlink {}: {}", path.display(), e),
                    )));
                }
                Ok(_) => {} // Regular file symlink, continue
            }
        }

        let metadata = std::fs::metadata(path)?;

        // Safety check: ensure we're not trying to hash a directory
        if metadata.is_dir() {
            return Err(RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::IsADirectory,
                format!("Cannot hash directory: {}", path.display()),
            )));
        }

        let cache_key = CacheKey {
            path: path.to_path_buf(),
            size: metadata.len(),
            modified: metadata
                .modified()
                .unwrap_or(std::time::SystemTime::UNIX_EPOCH),
        };

        // Check cache first
        if let Some(cached_hash) = self.cache.get(&cache_key) {
            debug!("Cache hit for {:?}", path);
            return Ok(cached_hash);
        }

        // Compute hash
        let mut file = std::fs::File::open(path).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to open file {}: {}", path.display(), e),
            ))
        })?;
        let mut hasher = blake3::Hasher::new();
        let mut buffer = vec![0; 64 * 1024]; // 64KB buffer

        loop {
            let n = file.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            hasher.update(&buffer[..n]);
        }

        let hash: Blake3Hash = hasher.finalize().into();

        // Store in cache
        self.cache.put(cache_key, hash);

        Ok(hash)
    }

    fn hash_reader(&self, mut reader: Box<dyn Read + Send>) -> Result<Blake3Hash, RCompareError> {
        let mut hasher = blake3::Hasher::new();
        let mut buffer = vec![0; 64 * 1024]; // 64KB buffer

        loop {
            let n = reader.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            hasher.update(&buffer[..n]);
        }

        Ok(hasher.finalize().into())
    }

    fn open_reader(
        &self,
        path: &Path,
        vfs: Option<&dyn Vfs>,
    ) -> Result<Box<dyn Read + Send>, RCompareError> {
        if let Some(vfs) = vfs {
            vfs.open_file(path).map_err(|e| {
                RCompareError::Vfs(format!("Failed to open {} from VFS: {}", path.display(), e))
            })
        } else {
            std::fs::File::open(path)
                .map(|f| Box::new(f) as Box<dyn Read + Send>)
                .map_err(|e| {
                    RCompareError::Io(std::io::Error::new(
                        e.kind(),
                        format!("Failed to open file {}: {}", path.display(), e),
                    ))
                })
        }
    }

    fn partial_hash_file(&self, path: &Path) -> Result<Blake3Hash, RCompareError> {
        const CHUNK_SIZE: usize = 16 * 1024;

        // Check for broken symlinks first
        let symlink_meta = std::fs::symlink_metadata(path).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to read metadata for {}: {}", path.display(), e),
            ))
        })?;

        if symlink_meta.file_type().is_symlink() {
            match std::fs::metadata(path) {
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    return Err(RCompareError::Io(std::io::Error::new(
                        std::io::ErrorKind::NotFound,
                        format!("Broken symlink (target does not exist): {}", path.display()),
                    )));
                }
                Err(e) => {
                    return Err(RCompareError::Io(std::io::Error::new(
                        e.kind(),
                        format!("Failed to follow symlink {}: {}", path.display(), e),
                    )));
                }
                Ok(_) => {} // Continue
            }
        }

        let mut file = std::fs::File::open(path).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to open file {}: {}", path.display(), e),
            ))
        })?;
        let metadata = file.metadata()?;

        // Safety check: ensure we're not trying to hash a directory
        if metadata.is_dir() {
            return Err(RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::IsADirectory,
                format!("Cannot hash directory: {}", path.display()),
            )));
        }

        let len = metadata.len();

        let mut hasher = blake3::Hasher::new();

        if len <= (CHUNK_SIZE as u64) * 3 {
            let mut buffer = Vec::with_capacity(len as usize);
            file.read_to_end(&mut buffer)?;
            hasher.update(&buffer);
        } else {
            let mut buffer = vec![0u8; CHUNK_SIZE];

            file.read_exact(&mut buffer)?;
            hasher.update(&buffer);

            let middle_offset = (len / 2).saturating_sub((CHUNK_SIZE / 2) as u64);
            file.seek(SeekFrom::Start(middle_offset))?;
            file.read_exact(&mut buffer)?;
            hasher.update(&buffer);

            let last_offset = len - CHUNK_SIZE as u64;
            file.seek(SeekFrom::Start(last_offset))?;
            file.read_exact(&mut buffer)?;
            hasher.update(&buffer);
        }

        Ok(hasher.finalize().into())
    }

    /// Verify two files by comparing their hashes
    pub fn verify_files(&self, left_path: &Path, right_path: &Path) -> Result<bool, RCompareError> {
        let left_hash = self.hash_file(left_path)?;
        let right_hash = self.hash_file(right_path)?;
        Ok(left_hash == right_hash)
    }

    /// Compare three lists of file entries (base, left, right) for three-way merge
    pub fn compare_three_way(
        &self,
        base_root: &Path,
        left_root: &Path,
        right_root: &Path,
        base_entries: Vec<FileEntry>,
        left_entries: Vec<FileEntry>,
        right_entries: Vec<FileEntry>,
    ) -> Result<Vec<ThreeWayDiffNode>, RCompareError> {
        self.compare_three_way_with_vfs(
            base_root,
            left_root,
            right_root,
            base_entries,
            left_entries,
            right_entries,
            None,
            None,
            None,
        )
    }

    /// Compare three lists with VFS support
    pub fn compare_three_way_with_vfs(
        &self,
        base_root: &Path,
        left_root: &Path,
        right_root: &Path,
        base_entries: Vec<FileEntry>,
        left_entries: Vec<FileEntry>,
        right_entries: Vec<FileEntry>,
        base_vfs: Option<&dyn Vfs>,
        left_vfs: Option<&dyn Vfs>,
        right_vfs: Option<&dyn Vfs>,
    ) -> Result<Vec<ThreeWayDiffNode>, RCompareError> {
        info!(
            "Three-way comparing: {} base, {} left, {} right entries",
            base_entries.len(),
            left_entries.len(),
            right_entries.len()
        );

        let mut base_map: HashMap<PathBuf, FileEntry> = base_entries
            .into_iter()
            .map(|e| (e.path.clone(), e))
            .collect();

        let mut left_map: HashMap<PathBuf, FileEntry> = left_entries
            .into_iter()
            .map(|e| (e.path.clone(), e))
            .collect();

        let mut right_map: HashMap<PathBuf, FileEntry> = right_entries
            .into_iter()
            .map(|e| (e.path.clone(), e))
            .collect();

        // Collect all unique paths
        let mut all_paths: Vec<PathBuf> = base_map
            .keys()
            .chain(left_map.keys())
            .chain(right_map.keys())
            .cloned()
            .collect();
        all_paths.sort();
        all_paths.dedup();

        let mut diff_nodes = Vec::new();

        for path in all_paths {
            let base = base_map.remove(&path);
            let left = left_map.remove(&path);
            let right = right_map.remove(&path);

            let status = self.three_way_status(
                base_root, left_root, right_root, base_vfs, left_vfs, right_vfs, &base, &left,
                &right,
            )?;

            diff_nodes.push(ThreeWayDiffNode {
                relative_path: path,
                base,
                left,
                right,
                status,
            });
        }

        debug!("Generated {} three-way diff nodes", diff_nodes.len());
        Ok(diff_nodes)
    }

    /// Determine the three-way diff status for a single path
    fn three_way_status(
        &self,
        base_root: &Path,
        left_root: &Path,
        right_root: &Path,
        base_vfs: Option<&dyn Vfs>,
        left_vfs: Option<&dyn Vfs>,
        right_vfs: Option<&dyn Vfs>,
        base: &Option<FileEntry>,
        left: &Option<FileEntry>,
        right: &Option<FileEntry>,
    ) -> Result<ThreeWayDiffStatus, RCompareError> {
        match (base, left, right) {
            // All three present
            (Some(b), Some(l), Some(r)) => {
                // Check if any are directories
                if b.is_dir && l.is_dir && r.is_dir {
                    return Ok(ThreeWayDiffStatus::AllSame);
                }
                if b.is_dir || l.is_dir || r.is_dir {
                    // Mixed dir/file - treat as both changed
                    return Ok(ThreeWayDiffStatus::BothChanged);
                }

                // Compare hashes/content
                let base_same_as_left =
                    self.files_same(base_root, left_root, base_vfs, left_vfs, b, l)?;
                let base_same_as_right =
                    self.files_same(base_root, right_root, base_vfs, right_vfs, b, r)?;
                let left_same_as_right =
                    self.files_same(left_root, right_root, left_vfs, right_vfs, l, r)?;

                if base_same_as_left && base_same_as_right {
                    Ok(ThreeWayDiffStatus::AllSame)
                } else if base_same_as_left && !base_same_as_right {
                    Ok(ThreeWayDiffStatus::RightChanged)
                } else if !base_same_as_left && base_same_as_right {
                    Ok(ThreeWayDiffStatus::LeftChanged)
                } else if left_same_as_right {
                    // Both changed but to the same thing
                    Ok(ThreeWayDiffStatus::BothChanged)
                } else {
                    // Conflict: both changed differently
                    Ok(ThreeWayDiffStatus::BothChanged)
                }
            }

            // Base only
            (Some(_), None, None) => Ok(ThreeWayDiffStatus::BaseOnly),

            // Left only
            (None, Some(_), None) => Ok(ThreeWayDiffStatus::LeftOnly),

            // Right only
            (None, None, Some(_)) => Ok(ThreeWayDiffStatus::RightOnly),

            // Base and left (deleted from right)
            (Some(_), Some(_), None) => Ok(ThreeWayDiffStatus::BaseAndLeft),

            // Base and right (deleted from left)
            (Some(_), None, Some(_)) => Ok(ThreeWayDiffStatus::BaseAndRight),

            // Left and right (both added - potential conflict or same addition)
            (None, Some(_l), Some(_r)) => {
                // TODO: Distinguish between conflict (different additions) and same addition
                Ok(ThreeWayDiffStatus::BothAdded)
            }

            // None present (shouldn't happen)
            (None, None, None) => Ok(ThreeWayDiffStatus::AllSame),
        }
    }

    /// Check if two files are the same (by hash or content)
    fn files_same(
        &self,
        root1: &Path,
        root2: &Path,
        vfs1: Option<&dyn Vfs>,
        vfs2: Option<&dyn Vfs>,
        entry1: &FileEntry,
        entry2: &FileEntry,
    ) -> Result<bool, RCompareError> {
        // Quick size check
        if entry1.size != entry2.size {
            return Ok(false);
        }

        if !self.verify_hashes {
            // If sizes match and timestamps match, assume same
            if entry1.modified == entry2.modified {
                return Ok(true);
            }
            // Can't determine without hash verification
            return Ok(false);
        }

        let path1 = root1.join(&entry1.path);
        let path2 = root2.join(&entry2.path);

        if vfs1.is_none() && vfs2.is_none() {
            return self.verify_files(&path1, &path2);
        }

        let reader1 = self.open_reader(&path1, vfs1)?;
        let reader2 = self.open_reader(&path2, vfs2)?;
        let hash1 = self.hash_reader(reader1)?;
        let hash2 = self.hash_reader(reader2)?;

        Ok(hash1 == hash2)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;
    use std::time::SystemTime;
    use tempfile::TempDir;

    #[test]
    fn test_comparison_basic() {
        let temp = TempDir::new().unwrap();
        let cache = HashCache::new(temp.path().to_path_buf()).unwrap();
        let engine = ComparisonEngine::new(cache);

        let left = vec![FileEntry {
            path: PathBuf::from("file1.txt"),
            size: 100,
            modified: SystemTime::now(),
            is_dir: false,
        }];

        let right = vec![FileEntry {
            path: PathBuf::from("file2.txt"),
            size: 200,
            modified: SystemTime::now(),
            is_dir: false,
        }];

        let diff = engine
            .compare(Path::new("left"), Path::new("right"), left, right)
            .unwrap();
        assert_eq!(diff.len(), 2);
    }
}
