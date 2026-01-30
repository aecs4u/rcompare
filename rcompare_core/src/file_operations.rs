use rayon::prelude::*;
use rcompare_common::{FileEntry, RCompareError};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use tracing::{debug, info};

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
}

/// File operations engine
pub struct FileOperations {
    dry_run: bool,
    use_trash: bool,
}

impl FileOperations {
    pub fn new(dry_run: bool, use_trash: bool) -> Self {
        Self { dry_run, use_trash }
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
            });
        }

        // Ensure destination directory exists
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }

        debug!("Copying {} to {}", source.display(), dest.display());
        let bytes = fs::copy(source, dest)?;

        // Preserve timestamps
        if let Ok(metadata) = fs::metadata(source) {
            if let Ok(modified) = metadata.modified() {
                let _ =
                    filetime::set_file_mtime(dest, filetime::FileTime::from_system_time(modified));
            }
        }

        info!(
            "Copied {} bytes from {} to {}",
            bytes,
            source.display(),
            dest.display()
        );

        Ok(OperationResult {
            source: source.to_path_buf(),
            destination: Some(dest.to_path_buf()),
            operation: FileOperation::Copy,
            success: true,
            error: None,
            bytes_processed: bytes,
        })
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
}
