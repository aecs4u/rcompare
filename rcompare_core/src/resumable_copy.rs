use rcompare_common::{Blake3Hash, RCompareError};
use serde::{Deserialize, Serialize};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use tracing::{debug, info, warn};

const CHUNK_SIZE: usize = 4 * 1024 * 1024; // 4MB chunks
const CHECKPOINT_INTERVAL: u64 = 100 * 1024 * 1024; // Checkpoint every 100MB
const RESUMABLE_THRESHOLD: u64 = 50 * 1024 * 1024; // Only use resumable for files >50MB

/// Checkpoint metadata for resumable copies
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CopyCheckpoint {
    /// Source file path
    pub source: PathBuf,
    /// Destination file path
    pub destination: PathBuf,
    /// Total file size in bytes
    pub total_size: u64,
    /// Bytes copied so far
    pub bytes_copied: u64,
    /// Source file hash (for verification)
    pub source_hash: Blake3Hash,
    /// Partial hash of bytes copied so far
    pub partial_hash: Blake3Hash,
    /// Timestamp of last checkpoint
    pub timestamp: u64,
}

impl CopyCheckpoint {
    /// Get the checkpoint file path for a copy operation
    fn checkpoint_path(checkpoint_dir: &Path, source: &Path, dest: &Path) -> PathBuf {
        let source_str = source.to_string_lossy();
        let dest_str = dest.to_string_lossy();
        let combined = format!("{}->{}", source_str, dest_str);
        let hash = blake3::hash(combined.as_bytes());
        checkpoint_dir.join(format!("checkpoint_{}.json", hex::encode(&hash.as_bytes()[..16])))
    }

    /// Load a checkpoint from disk
    pub fn load(checkpoint_dir: &Path, source: &Path, dest: &Path) -> Result<Option<Self>, RCompareError> {
        let path = Self::checkpoint_path(checkpoint_dir, source, dest);
        if !path.exists() {
            return Ok(None);
        }

        let data = fs::read_to_string(&path)?;
        let checkpoint: CopyCheckpoint = serde_json::from_str(&data)
            .map_err(|e| RCompareError::Serialization(format!("Failed to parse checkpoint: {}", e)))?;

        Ok(Some(checkpoint))
    }

    /// Save checkpoint to disk
    pub fn save(&self, checkpoint_dir: &Path) -> Result<(), RCompareError> {
        fs::create_dir_all(checkpoint_dir)?;
        let path = Self::checkpoint_path(checkpoint_dir, &self.source, &self.destination);
        let data = serde_json::to_string_pretty(self)
            .map_err(|e| RCompareError::Serialization(format!("Failed to serialize checkpoint: {}", e)))?;
        fs::write(&path, data)?;
        Ok(())
    }

    /// Delete checkpoint file
    pub fn delete(checkpoint_dir: &Path, source: &Path, dest: &Path) -> Result<(), RCompareError> {
        let path = Self::checkpoint_path(checkpoint_dir, source, dest);
        if path.exists() {
            fs::remove_file(&path)?;
        }
        Ok(())
    }
}

/// Resumable copy engine
pub struct ResumableCopy {
    checkpoint_dir: PathBuf,
}

impl ResumableCopy {
    pub fn new(checkpoint_dir: PathBuf) -> Self {
        Self { checkpoint_dir }
    }

    /// Compute partial hash for a file up to a given number of bytes
    fn partial_hash(&self, path: &Path, bytes: u64) -> Result<Blake3Hash, RCompareError> {
        let mut file = File::open(path)?;
        let mut hasher = blake3::Hasher::new();
        let mut buffer = vec![0u8; CHUNK_SIZE];
        let mut remaining = bytes;

        while remaining > 0 {
            let to_read = std::cmp::min(remaining, CHUNK_SIZE as u64) as usize;
            let bytes_read = file.read(&mut buffer[..to_read])?;
            if bytes_read == 0 {
                break;
            }
            hasher.update(&buffer[..bytes_read]);
            remaining -= bytes_read as u64;
        }

        Ok(Blake3Hash(*hasher.finalize().as_bytes()))
    }

    /// Full file hash
    fn full_hash(&self, path: &Path) -> Result<Blake3Hash, RCompareError> {
        let mut file = File::open(path)?;
        let mut hasher = blake3::Hasher::new();
        let mut buffer = vec![0u8; CHUNK_SIZE];

        loop {
            let bytes_read = file.read(&mut buffer)?;
            if bytes_read == 0 {
                break;
            }
            hasher.update(&buffer[..bytes_read]);
        }

        Ok(Blake3Hash(*hasher.finalize().as_bytes()))
    }

    /// Copy a file with resume capability
    pub fn copy_resumable(
        &self,
        source: &Path,
        dest: &Path,
        progress_callback: Option<Box<dyn Fn(u64, u64) + Send>>,
    ) -> Result<ResumableResult, RCompareError> {
        // Get source file size
        let source_metadata = fs::metadata(source)?;
        let total_size = source_metadata.len();

        // For small files, just do a regular copy
        if total_size < RESUMABLE_THRESHOLD {
            debug!(
                "File {} is smaller than threshold, using regular copy",
                source.display()
            );
            return self.copy_regular(source, dest);
        }

        // Check for existing checkpoint
        let checkpoint = CopyCheckpoint::load(&self.checkpoint_dir, source, dest)?;

        // Determine starting position
        let (start_pos, checkpoint_valid) = if let Some(ref cp) = checkpoint {
            // Verify checkpoint is for the same source file
            if cp.total_size != total_size {
                warn!(
                    "Checkpoint total size mismatch (checkpoint: {}, actual: {}), starting fresh",
                    cp.total_size, total_size
                );
                (0, false)
            } else if !dest.exists() {
                warn!(
                    "Checkpoint exists but destination file missing, starting fresh"
                );
                (0, false)
            } else {
                let dest_size = fs::metadata(dest)?.len();
                if dest_size != cp.bytes_copied {
                    warn!(
                        "Checkpoint bytes mismatch (checkpoint: {}, actual: {}), starting fresh",
                        cp.bytes_copied, dest_size
                    );
                    (0, false)
                } else {
                    // Verify partial hash matches
                    info!(
                        "Found checkpoint for {} at {} bytes, verifying...",
                        dest.display(),
                        cp.bytes_copied
                    );
                    let dest_partial_hash = self.partial_hash(dest, cp.bytes_copied)?;
                    if dest_partial_hash == cp.partial_hash {
                        info!("Checkpoint verified, resuming from {} bytes", cp.bytes_copied);
                        (cp.bytes_copied, true)
                    } else {
                        warn!("Checkpoint hash mismatch, starting fresh");
                        (0, false)
                    }
                }
            }
        } else {
            (0, false)
        };

        // Compute source hash
        let source_hash = self.full_hash(source)?;

        // If starting fresh, delete old partial file and checkpoint
        if start_pos == 0 && dest.exists() {
            debug!("Removing old partial file {}", dest.display());
            fs::remove_file(dest)?;
        }
        if !checkpoint_valid {
            CopyCheckpoint::delete(&self.checkpoint_dir, source, dest)?;
        }

        // Ensure destination directory exists
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }

        // Open source for reading
        let mut source_file = File::open(source)?;
        if start_pos > 0 {
            source_file.seek(SeekFrom::Start(start_pos))?;
        }

        // Open destination for writing
        let mut dest_file = if start_pos > 0 {
            OpenOptions::new().append(true).open(dest)?
        } else {
            File::create(dest)?
        };

        // Copy with checkpoints
        let mut buffer = vec![0u8; CHUNK_SIZE];
        let mut bytes_copied = start_pos;
        let mut hasher = blake3::Hasher::new();
        let mut last_checkpoint = start_pos;
        let resumed = start_pos > 0;

        // If resuming, we need to hash the already-copied bytes for the final verification
        if resumed {
            let mut temp_file = File::open(dest)?;
            let mut temp_buffer = vec![0u8; CHUNK_SIZE];
            let mut temp_read = 0;
            while temp_read < start_pos {
                let to_read = std::cmp::min((start_pos - temp_read) as usize, CHUNK_SIZE);
                let bytes_read = temp_file.read(&mut temp_buffer[..to_read])?;
                if bytes_read == 0 {
                    break;
                }
                hasher.update(&temp_buffer[..bytes_read]);
                temp_read += bytes_read as u64;
            }
        }

        loop {
            let bytes_read = source_file.read(&mut buffer)?;
            if bytes_read == 0 {
                break;
            }

            dest_file.write_all(&buffer[..bytes_read])?;
            hasher.update(&buffer[..bytes_read]);
            bytes_copied += bytes_read as u64;

            // Progress callback
            if let Some(ref callback) = progress_callback {
                callback(bytes_copied, total_size);
            }

            // Save checkpoint periodically
            if bytes_copied - last_checkpoint >= CHECKPOINT_INTERVAL {
                let partial_hash = Blake3Hash(*hasher.finalize().as_bytes());
                hasher = blake3::Hasher::new();

                // Re-hash everything up to this point for next checkpoint
                let mut temp_file = File::open(dest)?;
                let mut temp_buffer = vec![0u8; CHUNK_SIZE];
                loop {
                    let bytes_read = temp_file.read(&mut temp_buffer)?;
                    if bytes_read == 0 {
                        break;
                    }
                    hasher.update(&temp_buffer[..bytes_read]);
                }

                let checkpoint = CopyCheckpoint {
                    source: source.to_path_buf(),
                    destination: dest.to_path_buf(),
                    total_size,
                    bytes_copied,
                    source_hash,
                    partial_hash,
                    timestamp: std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .expect("system time before Unix epoch")
                        .as_secs(),
                };
                checkpoint.save(&self.checkpoint_dir)?;
                last_checkpoint = bytes_copied;
                debug!("Saved checkpoint at {} bytes", bytes_copied);
            }
        }

        // Flush and sync
        dest_file.sync_all()?;
        drop(dest_file);

        // Verify final hash
        let dest_hash = self.full_hash(dest)?;
        let verified = dest_hash == source_hash;

        if verified {
            info!(
                "Successfully copied {} bytes from {} to {} (resumed: {})",
                bytes_copied,
                source.display(),
                dest.display(),
                resumed
            );

            // Preserve timestamps
            if let Ok(modified) = source_metadata.modified() {
                let _ = filetime::set_file_mtime(dest, filetime::FileTime::from_system_time(modified));
            }

            // Delete checkpoint
            CopyCheckpoint::delete(&self.checkpoint_dir, source, dest)?;

            Ok(ResumableResult {
                success: true,
                bytes_copied,
                resumed,
                verified: true,
                source_hash,
                dest_hash,
                error: None,
            })
        } else {
            warn!(
                "Hash mismatch after copy: source={:?}, dest={:?}",
                source_hash, dest_hash
            );
            Ok(ResumableResult {
                success: false,
                bytes_copied,
                resumed,
                verified: false,
                source_hash,
                dest_hash,
                error: Some("Hash verification failed".to_string()),
            })
        }
    }

    /// Regular non-resumable copy for small files
    fn copy_regular(&self, source: &Path, dest: &Path) -> Result<ResumableResult, RCompareError> {
        // Ensure destination directory exists
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }

        let source_hash = self.full_hash(source)?;
        let bytes_copied = fs::copy(source, dest)?;
        let dest_hash = self.full_hash(dest)?;

        // Preserve timestamps
        if let Ok(metadata) = fs::metadata(source) {
            if let Ok(modified) = metadata.modified() {
                let _ = filetime::set_file_mtime(dest, filetime::FileTime::from_system_time(modified));
            }
        }

        Ok(ResumableResult {
            success: true,
            bytes_copied,
            resumed: false,
            verified: source_hash == dest_hash,
            source_hash,
            dest_hash,
            error: None,
        })
    }

    /// Clean up all checkpoints in the checkpoint directory
    pub fn cleanup_checkpoints(&self) -> Result<usize, RCompareError> {
        let mut count = 0;
        if self.checkpoint_dir.exists() {
            for entry in fs::read_dir(&self.checkpoint_dir)? {
                let entry = entry?;
                let path = entry.path();
                if path.is_file() && path.extension().and_then(|s| s.to_str()) == Some("json") {
                    fs::remove_file(&path)?;
                    count += 1;
                }
            }
        }
        Ok(count)
    }
}

/// Result of a resumable copy operation
#[derive(Debug, Clone)]
pub struct ResumableResult {
    pub success: bool,
    pub bytes_copied: u64,
    pub resumed: bool,
    pub verified: bool,
    pub source_hash: Blake3Hash,
    pub dest_hash: Blake3Hash,
    pub error: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_small_file_regular_copy() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.txt");
        let dest = temp.path().join("dest.txt");
        let checkpoint_dir = temp.path().join("checkpoints");

        // Create a small file (below threshold)
        let content = b"Small file content";
        fs::write(&source, content).unwrap();

        let engine = ResumableCopy::new(checkpoint_dir.clone());
        let result = engine.copy_resumable(&source, &dest, None).unwrap();

        assert!(result.success);
        assert_eq!(result.bytes_copied, content.len() as u64);
        assert!(!result.resumed);
        assert!(result.verified);
        assert!(dest.exists());
        assert_eq!(fs::read(&dest).unwrap(), content);
    }

    #[test]
    fn test_large_file_with_checkpoint() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.bin");
        let dest = temp.path().join("dest.bin");
        let checkpoint_dir = temp.path().join("checkpoints");

        // Create a file larger than threshold (60MB)
        let size = 60 * 1024 * 1024;
        let content: Vec<u8> = (0..size).map(|i| (i % 256) as u8).collect();
        fs::write(&source, &content).unwrap();

        let engine = ResumableCopy::new(checkpoint_dir.clone());
        let result = engine.copy_resumable(&source, &dest, None).unwrap();

        assert!(result.success);
        assert_eq!(result.bytes_copied, size as u64);
        assert!(!result.resumed);
        assert!(result.verified);
        assert_eq!(result.source_hash, result.dest_hash);
    }

    #[test]
    fn test_resume_from_checkpoint() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.bin");
        let dest = temp.path().join("dest.bin");
        let checkpoint_dir = temp.path().join("checkpoints");

        // Create a 120MB file
        let size = 120 * 1024 * 1024;
        let content: Vec<u8> = (0..size).map(|i| (i % 256) as u8).collect();
        fs::write(&source, &content).unwrap();

        let engine = ResumableCopy::new(checkpoint_dir.clone());

        // First, simulate a partial copy by manually creating checkpoint
        let partial_size = 50 * 1024 * 1024;
        fs::write(&dest, &content[..partial_size]).unwrap();

        let source_hash = engine.full_hash(&source).unwrap();
        let partial_hash = engine.partial_hash(&dest, partial_size as u64).unwrap();

        let checkpoint = CopyCheckpoint {
            source: source.clone(),
            destination: dest.clone(),
            total_size: size as u64,
            bytes_copied: partial_size as u64,
            source_hash,
            partial_hash,
            timestamp: 0,
        };
        checkpoint.save(&checkpoint_dir).unwrap();

        // Now resume
        let result = engine.copy_resumable(&source, &dest, None).unwrap();

        assert!(result.success);
        assert_eq!(result.bytes_copied, size as u64);
        assert!(result.resumed);
        assert!(result.verified);
        assert_eq!(fs::read(&dest).unwrap(), content);
    }

    #[test]
    fn test_checkpoint_cleanup() {
        let temp = TempDir::new().unwrap();
        let checkpoint_dir = temp.path().join("checkpoints");
        fs::create_dir_all(&checkpoint_dir).unwrap();

        // Create some fake checkpoints
        for i in 0..5 {
            fs::write(
                checkpoint_dir.join(format!("checkpoint_{}.json", i)),
                "{}",
            )
            .unwrap();
        }

        let engine = ResumableCopy::new(checkpoint_dir.clone());
        let count = engine.cleanup_checkpoints().unwrap();

        assert_eq!(count, 5);
        assert_eq!(fs::read_dir(&checkpoint_dir).unwrap().count(), 0);
    }

    #[test]
    fn test_invalid_checkpoint_starts_fresh() {
        let temp = TempDir::new().unwrap();
        let source = temp.path().join("source.bin");
        let dest = temp.path().join("dest.bin");
        let checkpoint_dir = temp.path().join("checkpoints");

        // Create a 60MB file
        let size = 60 * 1024 * 1024;
        let content: Vec<u8> = (0..size).map(|i| (i % 256) as u8).collect();
        fs::write(&source, &content).unwrap();

        let engine = ResumableCopy::new(checkpoint_dir.clone());

        // Create invalid checkpoint (wrong size)
        let checkpoint = CopyCheckpoint {
            source: source.clone(),
            destination: dest.clone(),
            total_size: 999,
            bytes_copied: 500,
            source_hash: Blake3Hash([0; 32]),
            partial_hash: Blake3Hash([0; 32]),
            timestamp: 0,
        };
        checkpoint.save(&checkpoint_dir).unwrap();

        // Should start fresh despite checkpoint
        let result = engine.copy_resumable(&source, &dest, None).unwrap();

        assert!(result.success);
        assert_eq!(result.bytes_copied, size as u64);
        assert!(!result.resumed); // Started fresh
        assert!(result.verified);
    }
}
