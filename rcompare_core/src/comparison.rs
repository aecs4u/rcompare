//! File and directory tree comparison engine.
//!
//! This module provides the core comparison logic for detecting differences between
//! file trees, including two-way and three-way comparisons. It uses BLAKE3 hashing
//! with persistent caching for efficient repeated comparisons.
//!
//! # Features
//!
//! - **Two-way comparison**: Compare files between left and right trees
//! - **Three-way comparison**: Compare files across base, left, and right trees
//! - **BLAKE3 hashing**: Fast, cryptographic-quality hashing with caching
//! - **Partial hash optimization**: Quick comparison using first N bytes
//! - **Hash verification**: Optional re-hashing to verify cache integrity
//! - **VFS support**: Works with both filesystem and virtual file systems
//! - **Cancellation**: Supports cancelling long-running comparisons
//!
//! # Comparison Logic
//!
//! The comparison engine determines file status by:
//! 1. Comparing file sizes (fastest check)
//! 2. Comparing modification times (if sizes match)
//! 3. Computing partial hashes (first 8KB) for quick detection
//! 4. Computing full hashes only when necessary
//!
//! # Examples
//!
//! Basic two-way comparison:
//!
//! ```no_run
//! use rcompare_core::{ComparisonEngine, FolderScanner};
//! use rcompare_core::hash_cache::HashCache;
//! use rcompare_common::AppConfig;
//! use std::path::Path;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
//! let engine = ComparisonEngine::new(cache);
//!
//! let scanner = FolderScanner::new(AppConfig::default());
//! let left_entries = scanner.scan(Path::new("/left"))?;
//! let right_entries = scanner.scan(Path::new("/right"))?;
//!
//! let diffs = engine.compare(
//!     Path::new("/left"),
//!     Path::new("/right"),
//!     left_entries,
//!     right_entries,
//! )?;
//!
//! for diff in &diffs {
//!     println!("{:?}: {}", diff.status, diff.path.display());
//! }
//! # Ok(())
//! # }
//! ```
//!
//! Three-way merge comparison:
//!
//! ```no_run
//! use rcompare_core::{ComparisonEngine, FolderScanner};
//! use rcompare_core::hash_cache::HashCache;
//! use rcompare_common::AppConfig;
//! use std::path::Path;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
//! let engine = ComparisonEngine::new(cache);
//!
//! let scanner = FolderScanner::new(AppConfig::default());
//! let base_entries = scanner.scan(Path::new("/base"))?;
//! let left_entries = scanner.scan(Path::new("/left"))?;
//! let right_entries = scanner.scan(Path::new("/right"))?;
//!
//! let diffs = engine.three_way_compare(
//!     Path::new("/base"),
//!     Path::new("/left"),
//!     Path::new("/right"),
//!     base_entries,
//!     left_entries,
//!     right_entries,
//! )?;
//! # Ok(())
//! # }
//! ```

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

/// Comparison engine for comparing file trees with BLAKE3 hashing and persistent caching.
///
/// The engine efficiently compares files using a combination of size, timestamp, and
/// hash comparisons. It supports both two-way and three-way comparisons, with optional
/// hash verification for cache integrity.
///
/// # Examples
///
/// ```no_run
/// use rcompare_core::ComparisonEngine;
/// use rcompare_core::hash_cache::HashCache;
/// use std::path::Path;
///
/// # fn main() -> Result<(), Box<dyn std::error::Error>> {
/// let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
/// let engine = ComparisonEngine::new(cache)
///     .with_hash_verification(true); // Enable hash verification
/// # Ok(())
/// # }
/// ```
pub struct ComparisonEngine {
    cache: HashCache,
    verify_hashes: bool,
    /// Threshold in bytes for using streaming comparison (default: 100MB)
    /// Files larger than this will be compared in chunks to avoid loading entirely into memory
    streaming_threshold: u64,
}

impl ComparisonEngine {
    /// Default streaming threshold: 100MB
    const DEFAULT_STREAMING_THRESHOLD: u64 = 100 * 1024 * 1024;

    pub fn new(cache: HashCache) -> Self {
        Self {
            cache,
            verify_hashes: false,
            streaming_threshold: Self::DEFAULT_STREAMING_THRESHOLD,
        }
    }

    pub fn with_hash_verification(mut self, enabled: bool) -> Self {
        self.verify_hashes = enabled;
        self
    }

    /// Set the threshold for streaming comparison (in bytes)
    /// Files larger than this will be compared using chunk-by-chunk streaming
    /// to avoid loading them entirely into memory. Default is 100MB.
    pub fn with_streaming_threshold(mut self, threshold: u64) -> Self {
        self.streaming_threshold = threshold;
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
        self.compare_with_vfs_and_progress::<fn(usize, usize)>(
            left_root,
            right_root,
            left_entries,
            right_entries,
            left_vfs,
            right_vfs,
            cancel,
            None,
        )
    }

    /// Compare directory entries with VFS support, cancellation, and progress callback
    ///
    /// # Arguments
    ///
    /// * `progress_fn` - Optional callback function that receives (current, total) progress updates
    pub fn compare_with_vfs_and_progress<F>(
        &self,
        left_root: &Path,
        right_root: &Path,
        left_entries: Vec<FileEntry>,
        right_entries: Vec<FileEntry>,
        left_vfs: Option<&dyn Vfs>,
        right_vfs: Option<&dyn Vfs>,
        cancel: Option<&AtomicBool>,
        progress_fn: Option<F>,
    ) -> Result<Vec<DiffNode>, RCompareError>
    where
        F: Fn(usize, usize),
    {
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

        let total = all_paths.len();

        for (idx, path) in all_paths.into_iter().enumerate() {
            if cancel.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
                return Err(RCompareError::Comparison(
                    "Comparison cancelled".to_string(),
                ));
            }

            // Report progress
            if let Some(ref progress) = progress_fn {
                progress(idx + 1, total);
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

            // For large files, use streaming comparison to avoid loading into memory
            let use_streaming = left.size >= self.streaming_threshold;

            let same = if use_streaming {
                debug!(
                    "Using streaming comparison for large files ({} bytes): {}",
                    left.size,
                    left_path.display()
                );
                match self.compare_files_streaming(&left_path, &right_path) {
                    Ok(result) => result,
                    Err(RCompareError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                        debug!("Skipping broken symlink during streaming comparison");
                        return Ok(DiffStatus::Different);
                    }
                    Err(e) => return Err(e),
                }
            } else {
                match self.verify_files(&left_path, &right_path) {
                    Ok(result) => result,
                    Err(RCompareError::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => {
                        debug!("Skipping broken symlink during verification");
                        return Ok(DiffStatus::Different);
                    }
                    Err(e) => return Err(e),
                }
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

    /// Compute hashes for multiple files in parallel using rayon
    ///
    /// This method processes a batch of files concurrently, utilizing multiple CPU cores
    /// for significant performance improvements (2-3x on 4-8 core systems).
    ///
    /// # Arguments
    ///
    /// * `paths` - Iterator of file paths to hash
    ///
    /// # Returns
    ///
    /// Vector of tuples: (path, Result<hash, error>)
    ///
    /// # Performance
    ///
    /// - Small files (<1MB): Minimal speedup due to overhead
    /// - Medium files (1-100MB): 2-3x speedup on 4+ cores
    /// - Large files (>100MB): Up to 4x speedup on 8+ cores
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use rcompare_core::ComparisonEngine;
    /// use rcompare_core::HashCache;
    /// use std::path::Path;
    ///
    /// # fn main() -> Result<(), Box<dyn std::error::Error>> {
    /// let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
    /// let engine = ComparisonEngine::new(cache);
    ///
    /// let paths = vec![
    ///     Path::new("file1.txt"),
    ///     Path::new("file2.txt"),
    ///     Path::new("file3.txt"),
    /// ];
    ///
    /// let results = engine.hash_files_parallel(paths.iter().map(|p| *p));
    /// for (path, result) in results {
    ///     match result {
    ///         Ok(hash) => println!("{}: {}", path.display(), hex::encode(hash)),
    ///         Err(e) => eprintln!("{}: Error - {}", path.display(), e),
    ///     }
    /// }
    /// # Ok(())
    /// # }
    /// ```
    pub fn hash_files_parallel<'a, I>(
        &self,
        paths: I,
    ) -> Vec<(&'a Path, Result<Blake3Hash, RCompareError>)>
    where
        I: IntoIterator<Item = &'a Path>,
    {
        use rayon::prelude::*;

        paths
            .into_iter()
            .collect::<Vec<_>>()
            .par_iter()
            .map(|path| (*path, self.hash_file(path)))
            .collect()
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

        // Compute hash - use larger buffer for better performance
        let mut file = std::fs::File::open(path).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to open file {}: {}", path.display(), e),
            ))
        })?;

        // For large files (>10MB), use a bigger buffer and parallel hashing
        // BLAKE3 automatically uses SIMD and can parallelize internally
        let file_size = metadata.len();
        let buffer_size = if file_size > 10 * 1024 * 1024 {
            1024 * 1024 // 1MB buffer for large files
        } else {
            64 * 1024 // 64KB buffer for small files
        };

        let mut hasher = blake3::Hasher::new();
        let mut buffer = vec![0; buffer_size];

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

    /// Compare two large files using streaming chunk-by-chunk comparison
    /// This avoids loading the entire files into memory, making it suitable for very large files (>100MB).
    /// Returns true if files are identical, false if different.
    /// Exits early on first chunk mismatch for better performance.
    fn compare_files_streaming(&self, left_path: &Path, right_path: &Path) -> Result<bool, RCompareError> {
        use std::fs::File;
        use std::io::Read;

        // Open both files
        let mut left_file = File::open(left_path).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to open left file {}: {}", left_path.display(), e),
            ))
        })?;

        let mut right_file = File::open(right_path).map_err(|e| {
            RCompareError::Io(std::io::Error::new(
                e.kind(),
                format!("Failed to open right file {}: {}", right_path.display(), e),
            ))
        })?;

        // Use 1MB chunks for streaming comparison
        const STREAM_CHUNK_SIZE: usize = 1024 * 1024;
        let mut left_buffer = vec![0u8; STREAM_CHUNK_SIZE];
        let mut right_buffer = vec![0u8; STREAM_CHUNK_SIZE];

        loop {
            let left_read = left_file.read(&mut left_buffer)?;
            let right_read = right_file.read(&mut right_buffer)?;

            // If read different amounts, files are different
            if left_read != right_read {
                debug!(
                    "Streaming comparison: read size mismatch ({} vs {}) for {} vs {}",
                    left_read,
                    right_read,
                    left_path.display(),
                    right_path.display()
                );
                return Ok(false);
            }

            // If reached EOF on both, files are identical
            if left_read == 0 {
                debug!(
                    "Streaming comparison: files identical {}",
                    left_path.display()
                );
                return Ok(true);
            }

            // Compare this chunk
            if left_buffer[..left_read] != right_buffer[..right_read] {
                debug!(
                    "Streaming comparison: chunk mismatch for {} vs {}",
                    left_path.display(),
                    right_path.display()
                );
                return Ok(false);
            }
        }
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
    use std::fs::File;
    use std::io::Write;
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

    #[test]
    fn test_parallel_hashing() {
        let temp = TempDir::new().unwrap();
        let cache = HashCache::new(temp.path().join("cache")).unwrap();
        let engine = ComparisonEngine::new(cache);

        // Create test files
        let file1 = temp.path().join("file1.txt");
        let file2 = temp.path().join("file2.txt");
        let file3 = temp.path().join("file3.txt");

        File::create(&file1)
            .unwrap()
            .write_all(b"content1")
            .unwrap();
        File::create(&file2)
            .unwrap()
            .write_all(b"content2")
            .unwrap();
        File::create(&file3)
            .unwrap()
            .write_all(b"content1")
            .unwrap(); // Same as file1

        let paths = vec![file1.as_path(), file2.as_path(), file3.as_path()];

        // Hash in parallel
        let results = engine.hash_files_parallel(paths.iter().copied());

        assert_eq!(results.len(), 3);

        // All should succeed
        assert!(results.iter().all(|(_, r)| r.is_ok()));

        // file1 and file3 should have same hash (same content)
        let hash1 = results[0].1.as_ref().unwrap();
        let hash2 = results[1].1.as_ref().unwrap();
        let hash3 = results[2].1.as_ref().unwrap();

        assert_eq!(hash1, hash3, "Files with same content should have same hash");
        assert_ne!(hash1, hash2, "Files with different content should have different hash");
    }

    #[test]
    fn test_parallel_hashing_with_errors() {
        let temp = TempDir::new().unwrap();
        let cache = HashCache::new(temp.path().join("cache")).unwrap();
        let engine = ComparisonEngine::new(cache);

        // Create one valid file and reference non-existent files
        let file1 = temp.path().join("file1.txt");
        let file2 = temp.path().join("nonexistent.txt");

        std::fs::File::create(&file1)
            .unwrap()
            .write_all(b"content")
            .unwrap();

        let paths = vec![file1.as_path(), file2.as_path()];

        // Hash in parallel
        let results = engine.hash_files_parallel(paths.iter().copied());

        assert_eq!(results.len(), 2);
        assert!(results[0].1.is_ok(), "First file should hash successfully");
        assert!(results[1].1.is_err(), "Second file should error (not found)");
    }

    #[test]
    fn test_streaming_comparison_identical_files() {
        let temp = tempfile::tempdir().unwrap();
        let cache = HashCache::new(temp.path().join("cache")).unwrap();
        let engine = ComparisonEngine::new(cache);

        let file1 = temp.path().join("file1.dat");
        let file2 = temp.path().join("file2.dat");

        // Create identical large content (2MB)
        let content = vec![42u8; 2 * 1024 * 1024];
        std::fs::write(&file1, &content).unwrap();
        std::fs::write(&file2, &content).unwrap();

        let result = engine.compare_files_streaming(&file1, &file2).unwrap();
        assert!(result, "Identical files should return true");
    }

    #[test]
    fn test_streaming_comparison_different_files() {
        let temp = tempfile::tempdir().unwrap();
        let cache = HashCache::new(temp.path().join("cache")).unwrap();
        let engine = ComparisonEngine::new(cache);

        let file1 = temp.path().join("file1.dat");
        let file2 = temp.path().join("file2.dat");

        // Create different large content (2MB each)
        let content1 = vec![42u8; 2 * 1024 * 1024];
        let content2 = vec![43u8; 2 * 1024 * 1024];
        std::fs::write(&file1, &content1).unwrap();
        std::fs::write(&file2, &content2).unwrap();

        let result = engine.compare_files_streaming(&file1, &file2).unwrap();
        assert!(!result, "Different files should return false");
    }

    #[test]
    fn test_streaming_comparison_different_sizes() {
        let temp = tempfile::tempdir().unwrap();
        let cache = HashCache::new(temp.path().join("cache")).unwrap();
        let engine = ComparisonEngine::new(cache);

        let file1 = temp.path().join("file1.dat");
        let file2 = temp.path().join("file2.dat");

        // Create files of different sizes
        let content1 = vec![42u8; 2 * 1024 * 1024];
        let content2 = vec![42u8; 1024 * 1024]; // Half the size
        std::fs::write(&file1, &content1).unwrap();
        std::fs::write(&file2, &content2).unwrap();

        let result = engine.compare_files_streaming(&file1, &file2).unwrap();
        assert!(!result, "Files of different sizes should return false");
    }

    #[test]
    fn test_streaming_threshold_configuration() {
        let temp = tempfile::tempdir().unwrap();
        let cache = HashCache::new(temp.path().join("cache")).unwrap();

        // Create engine with 1MB threshold
        let engine = ComparisonEngine::new(cache)
            .with_streaming_threshold(1024 * 1024);

        assert_eq!(engine.streaming_threshold, 1024 * 1024);
    }

    #[test]
    fn test_compare_files_uses_streaming_for_large_files() {
        use rcompare_common::FileEntry;
        use std::time::SystemTime;

        let temp = tempfile::tempdir().unwrap();
        let cache = HashCache::new(temp.path().join("cache")).unwrap();

        // Set threshold to 1MB, enable verification
        let engine = ComparisonEngine::new(cache)
            .with_streaming_threshold(1024 * 1024)
            .with_hash_verification(true);

        let file1 = temp.path().join("file1.dat");
        let file2 = temp.path().join("file2.dat");

        // Create identical 2MB files (above threshold)
        let content = vec![42u8; 2 * 1024 * 1024];
        std::fs::write(&file1, &content).unwrap();
        std::fs::write(&file2, &content).unwrap();

        let metadata1 = std::fs::metadata(&file1).unwrap();
        let metadata2 = std::fs::metadata(&file2).unwrap();

        let entry1 = FileEntry {
            path: "file1.dat".into(),
            size: metadata1.len(),
            modified: metadata1.modified().unwrap_or(SystemTime::UNIX_EPOCH),
            is_dir: false,
        };

        let entry2 = FileEntry {
            path: "file2.dat".into(),
            size: metadata2.len(),
            modified: metadata2.modified().unwrap_or(SystemTime::UNIX_EPOCH),
            is_dir: false,
        };

        let status = engine
            .compare_files(temp.path(), temp.path(), None, None, &entry1, &entry2)
            .unwrap();

        assert_eq!(status, DiffStatus::Same, "Large identical files should be detected as same using streaming");
    }
}
