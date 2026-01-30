use rayon::prelude::*;
use rcompare_common::{Blake3Hash, FileEntry, RCompareError};
use std::fs;
use std::io;
use std::io::Read;
use std::path::{Path, PathBuf};
use tracing::{debug, info, warn};

/// File operation types
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FileOperation {
    Copy,
    Move,
    Delete,
    TouchTimestamp,
}

/// Result of a file operation
#[derive(Debug, Clone)]
pub struct OperationResult {
    pub source: PathBuf,
    pub destination: Option<PathBuf>,
    pub operation: FileOperation,
    pub success: bool,
    pub error: Option<String>,
    pub bytes_processed: u64,
    /// Source file hash (if verification was enabled)
    pub source_hash: Option<Blake3Hash>,
    /// Destination file hash (if verification was enabled)
    pub dest_hash: Option<Blake3Hash>,
    /// Whether the copy was verified successfully
    pub verified: bool,
    /// Number of retry attempts made (if verification failed)
    pub retries: u32,
}

/// File operations engine
pub struct FileOperations {
    dry_run: bool,
    use_trash: bool,
    verify_copies: bool,
    max_retries: u32,
}

impl FileOperations {
    pub fn new(dry_run: bool, use_trash: bool) -> Self {
        Self {
            dry_run,
            use_trash,
            verify_copies: false,
            max_retries: 0,
        }
    }

    pub fn with_verification(dry_run: bool, use_trash: bool, verify: bool, max_retries: u32) -> Self {
        Self {
            dry_run,
            use_trash,
            verify_copies: verify,
            max_retries,
        }
    }

    /// Compute BLAKE3 hash for a file
    fn hash_file(&self, path: &Path) -> Result<Blake3Hash, RCompareError> {
        let metadata = fs::metadata(path)?;
        let file_size = metadata.len();

        // Use adaptive buffer sizing for better performance
        let buffer_size = if file_size > 10 * 1024 * 1024 {
            1024 * 1024 // 1MB buffer for large files
        } else {
            64 * 1024 // 64KB buffer for small files
        };

        let mut file = fs::File::open(path)?;
        let mut hasher = blake3::Hasher::new();
        let mut buffer = vec![0; buffer_size];

        loop {
            let bytes_read = file.read(&mut buffer)?;
            if bytes_read == 0 {
                break;
            }
            hasher.update(&buffer[..bytes_read]);
        }

        Ok(Blake3Hash(*hasher.finalize().as_bytes()))
    }

    /// Copy a file from source to destination
    pub fn copy_file(&self, source: &Path, dest: &Path) -> Result<OperationResult, RCompareError> {
        if self.dry_run {
            info!(
                "DRY RUN: Would copy {} to {}",
                source.display(),
                dest.display()
            );
            return Ok(OperationResult {
                source: source.to_path_buf(),
                destination: Some(dest.to_path_buf()),
                operation: FileOperation::Copy,
                success: true,
                error: None,
                bytes_processed: 0,
                source_hash: None,
                dest_hash: None,
                verified: false,
                retries: 0,
            });
        }

        // Ensure destination directory exists
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }

        // Hash source file if verification is enabled
        let source_hash = if self.verify_copies {
            debug!("Computing source hash for {}", source.display());
            Some(self.hash_file(source)?)
        } else {
            None
        };

        let mut retries = 0;
        let mut bytes;

        // Retry loop for copy with verification
        loop {
            debug!("Copying {} to {} (attempt {})", source.display(), dest.display(), retries + 1);
            bytes = fs::copy(source, dest)?;

            // Preserve timestamps
            if let Ok(metadata) = fs::metadata(source) {
                if let Ok(modified) = metadata.modified() {
                    let _ = filetime::set_file_mtime(dest, filetime::FileTime::from_system_time(modified));
                }
            }

            // Verify if enabled
            if self.verify_copies {
                debug!("Verifying copy for {}", dest.display());
                let dest_hash = self.hash_file(dest)?;

                if source_hash.as_ref() == Some(&dest_hash) {
                    info!(
                        "Copied and verified {} bytes from {} to {}",
                        bytes,
                        source.display(),
                        dest.display()
                    );
                    return Ok(OperationResult {
                        source: source.to_path_buf(),
                        destination: Some(dest.to_path_buf()),
                        operation: FileOperation::Copy,
                        success: true,
                        error: None,
                        bytes_processed: bytes,
                        source_hash,
                        dest_hash: Some(dest_hash),
                        verified: true,
                        retries,
                    });
                } else {
                    retries += 1;
                    if retries >= self.max_retries {
                        warn!(
                            "Hash mismatch after {} retries for {} -> {}",
                            retries,
                            source.display(),
                            dest.display()
                        );
                        return Ok(OperationResult {
                            source: source.to_path_buf(),
                            destination: Some(dest.to_path_buf()),
                            operation: FileOperation::Copy,
                            success: false,
                            error: Some(format!(
                                "Hash mismatch after {} retries (source: {:?}, dest: {:?})",
                                retries, source_hash, Some(dest_hash)
                            )),
                            bytes_processed: bytes,
                            source_hash,
                            dest_hash: Some(dest_hash),
                            verified: false,
                            retries,
                        });
                    }
                    warn!(
                        "Hash mismatch for {} -> {}, retrying ({}/{})",
                        source.display(),
                        dest.display(),
                        retries,
                        self.max_retries
                    );
                    // Delete the corrupted destination and retry
                    let _ = fs::remove_file(dest);
                    continue;
                }
            } else {
                // No verification
                info!(
                    "Copied {} bytes from {} to {}",
                    bytes,
                    source.display(),
                    dest.display()
                );
                return Ok(OperationResult {
                    source: source.to_path_buf(),
                    destination: Some(dest.to_path_buf()),
                    operation: FileOperation::Copy,
                    success: true,
                    error: None,
                    bytes_processed: bytes,
                    source_hash: None,
                    dest_hash: None,
                    verified: false,
                    retries: 0,
                });
            }
        }
    }

    /// Move a file from source to destination
    pub fn move_file(&self, source: &Path, dest: &Path) -> Result<OperationResult, RCompareError> {
        if self.dry_run {
            info!(
                "DRY RUN: Would move {} to {}",
                source.display(),
                dest.display()
            );
            return Ok(OperationResult {
                source: source.to_path_buf(),
                destination: Some(dest.to_path_buf()),
                operation: FileOperation::Move,
                success: true,
                error: None,
                bytes_processed: 0,
                source_hash: None,
                dest_hash: None,
                verified: false,
                retries: 0,
            });
        }

        // Ensure destination directory exists
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }

        debug!("Moving {} to {}", source.display(), dest.display());

        let metadata = fs::metadata(source)?;
        let bytes = metadata.len();

        // Try rename first (fast path for same filesystem)
        match fs::rename(source, dest) {
            Ok(_) => {
                info!("Moved {} to {} (rename)", source.display(), dest.display());
            }
            Err(e) => {
                // Check if error is cross-device (EXDEV on Unix, ERROR_NOT_SAME_DEVICE on Windows)
                #[cfg(unix)]
                let is_cross_device = e.raw_os_error() == Some(18); // EXDEV

                #[cfg(windows)]
                let is_cross_device = e.raw_os_error() == Some(17); // ERROR_NOT_SAME_DEVICE

                #[cfg(not(any(unix, windows)))]
                let is_cross_device = true; // On other platforms, try copy+delete on any rename failure

                if is_cross_device {
                    debug!("Cross-filesystem move detected, using copy+delete fallback");
                    // Copy the file
                    fs::copy(source, dest)?;
                    // Delete the source
                    fs::remove_file(source)?;
                    info!(
                        "Moved {} to {} (copy+delete)",
                        source.display(),
                        dest.display()
                    );
                } else {
                    // Some other error, propagate it
                    return Err(e.into());
                }
            }
        }

        Ok(OperationResult {
            source: source.to_path_buf(),
            destination: Some(dest.to_path_buf()),
            operation: FileOperation::Move,
            success: true,
            error: None,
            bytes_processed: bytes,
            source_hash: None,
            dest_hash: None,
            verified: false,
            retries: 0,
        })
    }

    /// Delete a file (with optional trash support)
    pub fn delete_file(&self, path: &Path) -> Result<OperationResult, RCompareError> {
        if self.dry_run {
            info!("DRY RUN: Would delete {}", path.display());
            return Ok(OperationResult {
                source: path.to_path_buf(),
                destination: None,
                operation: FileOperation::Delete,
                success: true,
                error: None,
                bytes_processed: 0,
                source_hash: None,
                dest_hash: None,
                verified: false,
                retries: 0,
            });
        }

        let metadata = fs::metadata(path)?;
        let bytes = metadata.len();

        if self.use_trash {
            debug!("Moving {} to trash", path.display());
            trash::delete(path).map_err(|e| RCompareError::Io(io::Error::other(e.to_string())))?;
            info!("Moved {} to trash", path.display());
        } else {
            debug!("Permanently deleting {}", path.display());
            fs::remove_file(path)?;
            info!("Deleted {}", path.display());
        }

        Ok(OperationResult {
            source: path.to_path_buf(),
            destination: None,
            operation: FileOperation::Delete,
            success: true,
            error: None,
            bytes_processed: bytes,
            source_hash: None,
            dest_hash: None,
            verified: false,
            retries: 0,
        })
    }

    /// Touch a file (sync timestamp from source to destination)
    pub fn touch_timestamp(
        &self,
        source: &Path,
        dest: &Path,
    ) -> Result<OperationResult, RCompareError> {
        if self.dry_run {
            info!(
                "DRY RUN: Would sync timestamp from {} to {}",
                source.display(),
                dest.display()
            );
            return Ok(OperationResult {
                source: source.to_path_buf(),
                destination: Some(dest.to_path_buf()),
                operation: FileOperation::TouchTimestamp,
                success: true,
                error: None,
                bytes_processed: 0,
                source_hash: None,
                dest_hash: None,
                verified: false,
                retries: 0,
            });
        }

        let source_meta = fs::metadata(source)?;
        let modified = source_meta.modified()?;

        debug!(
            "Syncing timestamp from {} to {}",
            source.display(),
            dest.display()
        );
        filetime::set_file_mtime(dest, filetime::FileTime::from_system_time(modified))
            .map_err(|e| RCompareError::Io(io::Error::other(e.to_string())))?;

        info!(
            "Synced timestamp from {} to {}",
            source.display(),
            dest.display()
        );

        Ok(OperationResult {
            source: source.to_path_buf(),
            destination: Some(dest.to_path_buf()),
            operation: FileOperation::TouchTimestamp,
            success: true,
            error: None,
            bytes_processed: 0,
            source_hash: None,
            dest_hash: None,
            verified: false,
            retries: 0,
        })
    }

    /// Batch copy files (parallel)
    pub fn batch_copy(&self, operations: Vec<(PathBuf, PathBuf)>) -> Vec<OperationResult> {
        operations
            .par_iter()
            .map(|(src, dest)| match self.copy_file(src, dest) {
                Ok(result) => result,
                Err(e) => OperationResult {
                    source: src.clone(),
                    destination: Some(dest.clone()),
                    operation: FileOperation::Copy,
                    success: false,
                    error: Some(e.to_string()),
                    bytes_processed: 0,
                    source_hash: None,
                    dest_hash: None,
                    verified: false,
                    retries: 0,
                },
            })
            .collect()
    }

    /// Batch delete files (parallel)
    pub fn batch_delete(&self, files: Vec<PathBuf>) -> Vec<OperationResult> {
        files
            .par_iter()
            .map(|path| match self.delete_file(path) {
                Ok(result) => result,
                Err(e) => OperationResult {
                    source: path.clone(),
                    destination: None,
                    operation: FileOperation::Delete,
                    success: false,
                    error: Some(e.to_string()),
                    bytes_processed: 0,
                    source_hash: None,
                    dest_hash: None,
                    verified: false,
                    retries: 0,
                },
            })
            .collect()
    }

    /// Synchronize files (copy newer or missing files)
    pub fn sync_bidirectional(
        &self,
        left_root: &Path,
        right_root: &Path,
        files: &[(FileEntry, Option<FileEntry>)],
    ) -> Vec<OperationResult> {
        files
            .par_iter()
            .filter_map(|(left, right)| {
                match (left, right) {
                    // File exists on both sides - compare timestamps
                    (left_entry, Some(right_entry)) => {
                        if left_entry.modified > right_entry.modified {
                            // Left is newer, copy to right
                            let src = left_root.join(&left_entry.path);
                            let dest = right_root.join(&right_entry.path);
                            Some(self.copy_file(&src, &dest))
                        } else if right_entry.modified > left_entry.modified {
                            // Right is newer, copy to left
                            let src = right_root.join(&right_entry.path);
                            let dest = left_root.join(&left_entry.path);
                            Some(self.copy_file(&src, &dest))
                        } else {
                            None // Files are same age
                        }
                    }
                    // File only on left - copy to right
                    (left_entry, None) => {
                        let src = left_root.join(&left_entry.path);
                        let dest = right_root.join(&left_entry.path);
                        Some(self.copy_file(&src, &dest))
                    }
                }
            })
            .filter_map(|result| result.ok())
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_copy_file() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.txt");
        let dest = temp.path().join("dest.txt");

        fs::write(&source, b"test content").unwrap();

        let ops = FileOperations::new(false, false);
        let result = ops.copy_file(&source, &dest).unwrap();

        assert!(result.success);
        assert!(dest.exists());
        assert_eq!(fs::read_to_string(&dest).unwrap(), "test content");
    }

    #[test]
    fn test_dry_run() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.txt");
        let dest = temp.path().join("dest.txt");

        fs::write(&source, b"test").unwrap();

        let ops = FileOperations::new(true, false);
        let result = ops.copy_file(&source, &dest).unwrap();

        assert!(result.success);
        assert!(!dest.exists()); // Dry run shouldn't actually copy
    }

    #[test]
    fn test_touch_timestamp() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.txt");
        let dest = temp.path().join("dest.txt");

        fs::write(&source, b"source").unwrap();
        fs::write(&dest, b"dest").unwrap();

        std::thread::sleep(std::time::Duration::from_millis(100));

        let ops = FileOperations::new(false, false);
        let _ = ops.touch_timestamp(&source, &dest);

        let source_meta = fs::metadata(&source).unwrap();
        let dest_meta = fs::metadata(&dest).unwrap();

        assert_eq!(
            source_meta.modified().unwrap(),
            dest_meta.modified().unwrap()
        );
    }

    #[test]
    fn test_copy_with_verification() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.txt");
        let dest = temp.path().join("dest.txt");

        fs::write(&source, b"test content for verification").unwrap();

        let ops = FileOperations::with_verification(false, false, true, 3);
        let result = ops.copy_file(&source, &dest).unwrap();

        assert!(result.success);
        assert!(dest.exists());
        assert_eq!(fs::read_to_string(&dest).unwrap(), "test content for verification");
        assert!(result.verified);
        assert!(result.source_hash.is_some());
        assert!(result.dest_hash.is_some());
        assert_eq!(result.source_hash, result.dest_hash);
        assert_eq!(result.retries, 0);
    }

    #[test]
    fn test_copy_without_verification() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.txt");
        let dest = temp.path().join("dest.txt");

        fs::write(&source, b"test content").unwrap();

        let ops = FileOperations::with_verification(false, false, false, 0);
        let result = ops.copy_file(&source, &dest).unwrap();

        assert!(result.success);
        assert!(dest.exists());
        assert!(!result.verified);
        assert!(result.source_hash.is_none());
        assert!(result.dest_hash.is_none());
        assert_eq!(result.retries, 0);
    }

    #[test]
    fn test_hash_file() {
        let temp = TempDir::new().unwrap();
        let file1 = temp.path().join("file1.txt");
        let file2 = temp.path().join("file2.txt");
        let file3 = temp.path().join("file3.txt");

        fs::write(&file1, b"identical content").unwrap();
        fs::write(&file2, b"identical content").unwrap();
        fs::write(&file3, b"different content").unwrap();

        let ops = FileOperations::new(false, false);
        let hash1 = ops.hash_file(&file1).unwrap();
        let hash2 = ops.hash_file(&file2).unwrap();
        let hash3 = ops.hash_file(&file3).unwrap();

        // Same content should produce same hash
        assert_eq!(hash1, hash2);
        // Different content should produce different hash
        assert_ne!(hash1, hash3);
    }
}
