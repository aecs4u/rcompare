use crate::{FileEntry, FileMetadata, VfsError};
use std::io::{Read, Write};
use std::path::Path;
use std::time::SystemTime;

/// Virtual File System trait for abstracting filesystem operations
///
/// This trait allows RCompare to treat local filesystems, archives (ZIP, TAR),
/// and potentially remote sources (FTP, S3) uniformly.
pub trait Vfs: Send + Sync {
    /// Uniquely identifies the VFS instance (e.g., "local", "zip:archive.zip")
    fn instance_id(&self) -> &str;

    /// Returns the metadata for a specific path
    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError>;

    /// Lists the contents of a directory
    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError>;

    /// Opens a file for reading (returns a Read trait object)
    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError>;

    /// Removes a file
    fn remove_file(&self, path: &Path) -> Result<(), VfsError>;

    /// Copies a file from src to dest
    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError>;

    /// Checks if a path exists
    fn exists(&self, path: &Path) -> bool {
        self.metadata(path).is_ok()
    }

    /// Check if this VFS supports write operations
    fn is_writable(&self) -> bool {
        false
    }

    /// Get the capabilities of this VFS
    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities::default()
    }

    /// Create a new file and return a writer
    /// Returns Unsupported error if not writable
    fn create_file(&self, _path: &Path) -> Result<Box<dyn Write + Send>, VfsError> {
        Err(VfsError::Unsupported("Write operations not supported".to_string()))
    }

    /// Create a directory
    fn create_dir(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Write operations not supported".to_string()))
    }

    /// Create a directory and all parent directories
    fn create_dir_all(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Write operations not supported".to_string()))
    }

    /// Rename/move a file or directory
    fn rename(&self, _from: &Path, _to: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Write operations not supported".to_string()))
    }

    /// Set file modification time
    fn set_mtime(&self, _path: &Path, _mtime: SystemTime) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Write operations not supported".to_string()))
    }

    /// Write file content from bytes
    fn write_file(&self, path: &Path, content: &[u8]) -> Result<(), VfsError> {
        let mut writer = self.create_file(path)?;
        writer.write_all(content).map_err(VfsError::Io)?;
        Ok(())
    }

    /// Flush any pending writes (for archives, this may rebuild the archive)
    fn flush(&self) -> Result<(), VfsError> {
        Ok(())
    }
}

/// Capabilities flags for VFS implementations
#[derive(Debug, Clone, Copy, Default)]
pub struct VfsCapabilities {
    pub read: bool,
    pub write: bool,
    pub delete: bool,
    pub rename: bool,
    pub create_dir: bool,
    pub set_mtime: bool,
}

impl VfsCapabilities {
    /// Full read-write capabilities (local filesystem)
    pub fn full() -> Self {
        Self {
            read: true,
            write: true,
            delete: true,
            rename: true,
            create_dir: true,
            set_mtime: true,
        }
    }

    /// Read-only capabilities
    pub fn read_only() -> Self {
        Self {
            read: true,
            write: false,
            delete: false,
            rename: false,
            create_dir: false,
            set_mtime: false,
        }
    }
}
