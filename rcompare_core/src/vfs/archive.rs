use rcompare_common::{FileEntry, FileMetadata, Vfs, VfsCapabilities, VfsError};
use super::local::LocalVfs;
use std::io::{Read, Write, Cursor};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::SystemTime;
use zip::{ZipArchive, ZipWriter};
use zip::write::FileOptions;
use std::fs::File;
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::Compression;
use sevenz_rust::decompress_file;
use bzip2::read::BzDecoder;
use bzip2::write::BzEncoder;
use xz2::read::XzDecoder;
use xz2::write::XzEncoder;
use unrar::Archive;

/// ZIP archive VFS implementation (read-only)
pub struct ZipVfs {
    instance_id: String,
    archive_path: PathBuf,
}

/// Writable ZIP archive VFS implementation
/// Uses a temp directory for modifications, rebuilds archive on flush()
pub struct WritableZipVfs {
    instance_id: String,
    archive_path: PathBuf,
    temp_dir: Arc<Mutex<tempfile::TempDir>>,
    local_vfs: LocalVfs,
    modified: Arc<Mutex<bool>>,
}

impl ZipVfs {
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        if !archive_path.exists() {
            return Err(VfsError::NotFound(archive_path.display().to_string()));
        }

        let instance_id = format!("zip:{}", archive_path.display());
        Ok(Self {
            instance_id,
            archive_path,
        })
    }

    fn open_archive(&self) -> Result<ZipArchive<File>, VfsError> {
        let file = File::open(&self.archive_path)?;
        ZipArchive::new(file)
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidData, e)))
    }
}

impl Vfs for ZipVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let mut archive = self.open_archive()?;
        let path_str = path.to_string_lossy();

        for i in 0..archive.len() {
            let file = archive.by_index(i)
                .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

            if file.name() == path_str.as_ref() {
                return Ok(FileMetadata {
                    size: file.size(),
                    modified: file.last_modified().to_time()
                        .map(|dt| {
                            let timestamp = dt.unix_timestamp();
                            SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(timestamp as u64)
                        })
                        .unwrap_or(SystemTime::UNIX_EPOCH),
                    is_dir: file.is_dir(),
                    is_symlink: false,
                });
            }
        }

        Err(VfsError::NotFound(path.display().to_string()))
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let mut archive = self.open_archive()?;
        let mut entries = Vec::new();
        let path_str = path.to_string_lossy();
        let prefix = if path_str.is_empty() {
            String::new()
        } else {
            format!("{}/", path_str)
        };

        for i in 0..archive.len() {
            let file = archive.by_index(i)
                .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

            let name = file.name();
            if name.starts_with(&prefix) {
                let relative = &name[prefix.len()..];

                // Only include direct children
                if !relative.is_empty() && !relative.contains('/') {
                    entries.push(FileEntry {
                        path: PathBuf::from(name),
                        size: file.size(),
                        modified: file.last_modified().to_time()
                            .map(|dt| {
                                let timestamp = dt.unix_timestamp();
                                SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(timestamp as u64)
                            })
                            .unwrap_or(SystemTime::UNIX_EPOCH),
                        is_dir: file.is_dir(),
                    });
                }
            }
        }

        Ok(entries)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let mut archive = self.open_archive()?;
        let path_str = path.to_string_lossy();

        let mut file = archive.by_name(&path_str)
            .map_err(|_| VfsError::NotFound(path.display().to_string()))?;

        if file.is_dir() {
            return Err(VfsError::NotAFile(path.display().to_string()));
        }

        let mut contents = Vec::new();
        file.read_to_end(&mut contents)?;

        Ok(Box::new(Cursor::new(contents)))
    }

    fn remove_file(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("ZIP archives are read-only".to_string()))
    }

    fn copy_file(&self, _src: &Path, _dest: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("ZIP archives are read-only".to_string()))
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities::read_only()
    }
}

impl WritableZipVfs {
    /// Create a writable ZIP VFS from an existing archive
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        // Extract existing archive if it exists
        if archive_path.exists() {
            let file = File::open(&archive_path)?;
            let mut archive = ZipArchive::new(file)
                .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidData, e)))?;

            archive.extract(temp_dir.path())
                .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;
        }

        let instance_id = format!("zip-rw:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            archive_path,
            temp_dir: Arc::new(Mutex::new(temp_dir)),
            local_vfs,
            modified: Arc::new(Mutex::new(false)),
        })
    }

    /// Create a new empty writable ZIP archive
    pub fn create(archive_path: PathBuf) -> Result<Self, VfsError> {
        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        let instance_id = format!("zip-rw:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            archive_path,
            temp_dir: Arc::new(Mutex::new(temp_dir)),
            local_vfs,
            modified: Arc::new(Mutex::new(true)), // Mark as modified for new archives
        })
    }

    fn mark_modified(&self) {
        if let Ok(mut modified) = self.modified.lock() {
            *modified = true;
        }
    }

    fn rebuild_archive(&self) -> Result<(), VfsError> {
        let temp_dir = self.temp_dir.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock temp dir")))?;

        let file = File::create(&self.archive_path)?;
        let mut zip = ZipWriter::new(file);
        let options = FileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);

        // Walk the temp directory and add all files
        add_directory_to_zip(&mut zip, temp_dir.path(), temp_dir.path(), options)?;

        zip.finish()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        Ok(())
    }
}

fn add_directory_to_zip(
    zip: &mut ZipWriter<File>,
    base_path: &Path,
    current_path: &Path,
    options: FileOptions,
) -> Result<(), VfsError> {
    for entry in std::fs::read_dir(current_path)? {
        let entry = entry?;
        let path = entry.path();
        let relative_path = path.strip_prefix(base_path)
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Path strip failed")))?;

        if path.is_dir() {
            // Add directory entry
            let dir_name = format!("{}/", relative_path.to_string_lossy());
            zip.add_directory(&dir_name, options)
                .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;
            // Recurse into directory
            add_directory_to_zip(zip, base_path, &path, options)?;
        } else {
            // Add file entry
            let file_name = relative_path.to_string_lossy();
            zip.start_file(file_name.as_ref(), options)
                .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;
            let content = std::fs::read(&path)?;
            zip.write_all(&content)?;
        }
    }
    Ok(())
}

impl Vfs for WritableZipVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        self.local_vfs.metadata(path)
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        self.local_vfs.read_dir(path)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        self.local_vfs.open_file(path)
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.remove_file(path)
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.copy_file(src, dest)
    }

    fn is_writable(&self) -> bool {
        true
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities {
            read: true,
            write: true,
            delete: true,
            rename: true,
            create_dir: true,
            set_mtime: true,
        }
    }

    fn create_file(&self, path: &Path) -> Result<Box<dyn Write + Send>, VfsError> {
        self.mark_modified();
        self.local_vfs.create_file(path)
    }

    fn create_dir(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.create_dir(path)
    }

    fn create_dir_all(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.create_dir_all(path)
    }

    fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.rename(from, to)
    }

    fn set_mtime(&self, path: &Path, mtime: SystemTime) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.set_mtime(path, mtime)
    }

    fn flush(&self) -> Result<(), VfsError> {
        let modified = self.modified.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock modified flag")))?;

        if *modified {
            drop(modified); // Release lock before rebuilding
            self.rebuild_archive()?;

            // Reset modified flag
            if let Ok(mut modified) = self.modified.lock() {
                *modified = false;
            }
        }
        Ok(())
    }
}

/// TAR archive VFS implementation (read-only)
pub struct TarVfs {
    instance_id: String,
    archive_path: PathBuf,
}

/// Writable TAR archive VFS implementation
/// Uses a temp directory for modifications, rebuilds archive on flush()
pub struct WritableTarVfs {
    instance_id: String,
    archive_path: PathBuf,
    temp_dir: Arc<Mutex<tempfile::TempDir>>,
    local_vfs: LocalVfs,
    modified: Arc<Mutex<bool>>,
    compress_gzip: bool,
}

impl TarVfs {
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        if !archive_path.exists() {
            return Err(VfsError::NotFound(archive_path.display().to_string()));
        }

        let instance_id = format!("tar:{}", archive_path.display());
        Ok(Self {
            instance_id,
            archive_path,
        })
    }

    fn open_archive(&self) -> Result<tar::Archive<Box<dyn Read>>, VfsError> {
        let file = File::open(&self.archive_path)?;
        if is_gzip_archive(&self.archive_path) {
            let decoder = GzDecoder::new(file);
            Ok(tar::Archive::new(Box::new(decoder)))
        } else {
            Ok(tar::Archive::new(Box::new(file)))
        }
    }
}

impl Vfs for TarVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let mut archive = self.open_archive()?;
        for entry in archive.entries()? {
            let entry = entry?;
            let entry_path = entry.path()?;

            if entry_path == path {
                let header = entry.header();
                return Ok(FileMetadata {
                    size: header.size()?,
                    modified: SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(header.mtime()?),
                    is_dir: header.entry_type().is_dir(),
                    is_symlink: header.entry_type() == tar::EntryType::Symlink,
                });
            }
        }

        Err(VfsError::NotFound(path.display().to_string()))
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let mut archive = self.open_archive()?;
        let mut entries = Vec::new();
        for entry in archive.entries()? {
            let entry = entry?;
            let entry_path = entry.path()?;

            if let Some(parent) = entry_path.parent() {
                if parent == path {
                    let header = entry.header();
                    entries.push(FileEntry {
                        path: entry_path.to_path_buf(),
                        size: header.size()?,
                        modified: SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(header.mtime()?),
                        is_dir: header.entry_type().is_dir(),
                    });
                }
            }
        }

        Ok(entries)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let mut archive = self.open_archive()?;

        for entry in archive.entries()? {
            let mut entry = entry?;
            let entry_path = entry.path()?;

            if entry_path == path {
                let mut contents = Vec::new();
                entry.read_to_end(&mut contents)?;
                return Ok(Box::new(Cursor::new(contents)));
            }
        }

        Err(VfsError::NotFound(path.display().to_string()))
    }

    fn remove_file(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("TAR archives are read-only".to_string()))
    }

    fn copy_file(&self, _src: &Path, _dest: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("TAR archives are read-only".to_string()))
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities::read_only()
    }
}

impl WritableTarVfs {
    /// Create a writable TAR VFS from an existing archive
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        let compress_gzip = is_gzip_archive(&archive_path);
        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        // Extract existing archive if it exists
        if archive_path.exists() {
            let file = File::open(&archive_path)?;
            let mut archive: tar::Archive<Box<dyn Read>> = if compress_gzip {
                let decoder = GzDecoder::new(file);
                tar::Archive::new(Box::new(decoder))
            } else {
                tar::Archive::new(Box::new(file))
            };

            archive.unpack(temp_dir.path())?;
        }

        let instance_id = format!("tar-rw:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            archive_path,
            temp_dir: Arc::new(Mutex::new(temp_dir)),
            local_vfs,
            modified: Arc::new(Mutex::new(false)),
            compress_gzip,
        })
    }

    /// Create a new empty writable TAR archive
    pub fn create(archive_path: PathBuf) -> Result<Self, VfsError> {
        let compress_gzip = is_gzip_archive(&archive_path);
        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        let instance_id = format!("tar-rw:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            archive_path,
            temp_dir: Arc::new(Mutex::new(temp_dir)),
            local_vfs,
            modified: Arc::new(Mutex::new(true)),
            compress_gzip,
        })
    }

    fn mark_modified(&self) {
        if let Ok(mut modified) = self.modified.lock() {
            *modified = true;
        }
    }

    fn rebuild_archive(&self) -> Result<(), VfsError> {
        let temp_dir = self.temp_dir.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock temp dir")))?;

        let file = File::create(&self.archive_path)?;

        if self.compress_gzip {
            let encoder = GzEncoder::new(file, Compression::default());
            let mut builder = tar::Builder::new(encoder);
            builder.append_dir_all("", temp_dir.path())?;
            builder.finish()?;
        } else {
            let mut builder = tar::Builder::new(file);
            builder.append_dir_all("", temp_dir.path())?;
            builder.finish()?;
        }

        Ok(())
    }
}

impl Vfs for WritableTarVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        self.local_vfs.metadata(path)
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        self.local_vfs.read_dir(path)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        self.local_vfs.open_file(path)
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.remove_file(path)
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.copy_file(src, dest)
    }

    fn is_writable(&self) -> bool {
        true
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities {
            read: true,
            write: true,
            delete: true,
            rename: true,
            create_dir: true,
            set_mtime: true,
        }
    }

    fn create_file(&self, path: &Path) -> Result<Box<dyn Write + Send>, VfsError> {
        self.mark_modified();
        self.local_vfs.create_file(path)
    }

    fn create_dir(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.create_dir(path)
    }

    fn create_dir_all(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.create_dir_all(path)
    }

    fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.rename(from, to)
    }

    fn set_mtime(&self, path: &Path, mtime: SystemTime) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.set_mtime(path, mtime)
    }

    fn flush(&self) -> Result<(), VfsError> {
        let modified = self.modified.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock modified flag")))?;

        if *modified {
            drop(modified);
            self.rebuild_archive()?;

            if let Ok(mut modified) = self.modified.lock() {
                *modified = false;
            }
        }
        Ok(())
    }
}

/// 7Z archive VFS implementation (read-only, extracted to temp dir)
pub struct SevenZVfs {
    instance_id: String,
    _temp_dir: tempfile::TempDir,
    local_vfs: LocalVfs,
}

/// Writable 7Z archive VFS implementation
/// Uses a temp directory for modifications, rebuilds archive on flush()
pub struct Writable7zVfs {
    instance_id: String,
    archive_path: PathBuf,
    temp_dir: Arc<Mutex<tempfile::TempDir>>,
    local_vfs: LocalVfs,
    modified: Arc<Mutex<bool>>,
}

/// RAR archive VFS implementation (read-only, extracted to temp dir)
/// Requires unrar library to be installed on the system
pub struct RarVfs {
    instance_id: String,
    _temp_dir: tempfile::TempDir,
    local_vfs: LocalVfs,
}

impl SevenZVfs {
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        if !archive_path.exists() {
            return Err(VfsError::NotFound(archive_path.display().to_string()));
        }

        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        decompress_file(&archive_path, temp_dir.path())
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidData, e.to_string())))?;

        let instance_id = format!("7z:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            _temp_dir: temp_dir,
            local_vfs,
        })
    }
}

impl Vfs for SevenZVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        self.local_vfs.metadata(path)
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        self.local_vfs.read_dir(path)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        self.local_vfs.open_file(path)
    }

    fn remove_file(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("7Z archives are read-only".to_string()))
    }

    fn copy_file(&self, _src: &Path, _dest: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("7Z archives are read-only".to_string()))
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities::read_only()
    }
}

impl Writable7zVfs {
    /// Create a writable 7Z VFS from an existing archive
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        // Extract existing archive if it exists
        if archive_path.exists() {
            decompress_file(&archive_path, temp_dir.path())
                .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidData, e.to_string())))?;
        }

        let instance_id = format!("7z-rw:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            archive_path,
            temp_dir: Arc::new(Mutex::new(temp_dir)),
            local_vfs,
            modified: Arc::new(Mutex::new(false)),
        })
    }

    /// Create a new empty writable 7Z archive
    pub fn create(archive_path: PathBuf) -> Result<Self, VfsError> {
        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        let instance_id = format!("7z-rw:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            archive_path,
            temp_dir: Arc::new(Mutex::new(temp_dir)),
            local_vfs,
            modified: Arc::new(Mutex::new(true)),
        })
    }

    fn mark_modified(&self) {
        if let Ok(mut modified) = self.modified.lock() {
            *modified = true;
        }
    }

    fn rebuild_archive(&self) -> Result<(), VfsError> {
        let temp_dir = self.temp_dir.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock temp dir")))?;

        // Use sevenz_rust to compress the directory
        sevenz_rust::compress_to_path(temp_dir.path(), &self.archive_path)
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string())))?;

        Ok(())
    }
}

impl Vfs for Writable7zVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        self.local_vfs.metadata(path)
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        self.local_vfs.read_dir(path)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        self.local_vfs.open_file(path)
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.remove_file(path)
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.copy_file(src, dest)
    }

    fn is_writable(&self) -> bool {
        true
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities {
            read: true,
            write: true,
            delete: true,
            rename: true,
            create_dir: true,
            set_mtime: true,
        }
    }

    fn create_file(&self, path: &Path) -> Result<Box<dyn Write + Send>, VfsError> {
        self.mark_modified();
        self.local_vfs.create_file(path)
    }

    fn create_dir(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.create_dir(path)
    }

    fn create_dir_all(&self, path: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.create_dir_all(path)
    }

    fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.rename(from, to)
    }

    fn set_mtime(&self, path: &Path, mtime: SystemTime) -> Result<(), VfsError> {
        self.mark_modified();
        self.local_vfs.set_mtime(path, mtime)
    }

    fn flush(&self) -> Result<(), VfsError> {
        let modified = self.modified.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock modified flag")))?;

        if *modified {
            drop(modified);
            self.rebuild_archive()?;

            if let Ok(mut modified) = self.modified.lock() {
                *modified = false;
            }
        }
        Ok(())
    }
}

impl RarVfs {
    /// Create a RAR VFS by extracting to a temp directory
    /// Returns error if unrar library is not available
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        if !archive_path.exists() {
            return Err(VfsError::NotFound(archive_path.display().to_string()));
        }

        let temp_dir = tempfile::TempDir::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e)))?;

        // Extract RAR archive to temp directory
        let mut archive = Archive::new(&archive_path)
            .open_for_processing()
            .map_err(|e: unrar::error::UnrarError| {
                VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidData, e.to_string()))
            })?;

        // Process each entry and extract
        while let Some(header) = archive.read_header()
            .map_err(|e: unrar::error::UnrarError| {
                VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))
            })?
        {
            archive = header.extract_to(temp_dir.path())
                .map_err(|e: unrar::error::UnrarError| {
                    VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string()))
                })?;
        }

        let instance_id = format!("rar:{}", archive_path.display());
        let local_vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        Ok(Self {
            instance_id,
            _temp_dir: temp_dir,
            local_vfs,
        })
    }

    /// Check if RAR support is available on the system
    pub fn is_available() -> bool {
        // The unrar crate will fail if the library is not installed
        // This is a simple check - actual availability is tested on first use
        true
    }
}

impl Vfs for RarVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        self.local_vfs.metadata(path)
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        self.local_vfs.read_dir(path)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        self.local_vfs.open_file(path)
    }

    fn remove_file(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("RAR archives are read-only".to_string()))
    }

    fn copy_file(&self, _src: &Path, _dest: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("RAR archives are read-only".to_string()))
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities::read_only()
    }
}

fn is_gzip_archive(path: &Path) -> bool {
    let name = match path.file_name() {
        Some(name) => name.to_string_lossy().to_lowercase(),
        None => return false,
    };

    name.ends_with(".tar.gz") || name.ends_with(".tgz")
}

/// Compression type for single-file compressed formats
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum CompressionType {
    Gzip,
    Bzip2,
    Xz,
}

impl CompressionType {
    /// Detect compression type from file extension
    pub fn from_path(path: &Path) -> Option<Self> {
        let name = path.file_name()?.to_string_lossy().to_lowercase();
        if name.ends_with(".gz") && !name.ends_with(".tar.gz") {
            Some(CompressionType::Gzip)
        } else if name.ends_with(".bz2") && !name.ends_with(".tar.bz2") {
            Some(CompressionType::Bzip2)
        } else if name.ends_with(".xz") && !name.ends_with(".tar.xz") {
            Some(CompressionType::Xz)
        } else {
            None
        }
    }

    /// Get the extension for this compression type
    pub fn extension(&self) -> &'static str {
        match self {
            CompressionType::Gzip => ".gz",
            CompressionType::Bzip2 => ".bz2",
            CompressionType::Xz => ".xz",
        }
    }
}

/// VFS for single-file compressed formats (.gz, .bz2, .xz)
/// Exposes the decompressed content as a virtual file
pub struct CompressedFileVfs {
    instance_id: String,
    archive_path: PathBuf,
    inner_filename: String,
    compression_type: CompressionType,
}

impl CompressedFileVfs {
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        if !archive_path.exists() {
            return Err(VfsError::NotFound(archive_path.display().to_string()));
        }

        let compression_type = CompressionType::from_path(&archive_path)
            .ok_or_else(|| VfsError::Unsupported("Unknown compression type".to_string()))?;

        // Derive inner filename by removing the compression extension
        let filename = archive_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();

        let inner_filename = filename
            .strip_suffix(compression_type.extension())
            .unwrap_or(&filename)
            .to_string();

        let instance_id = format!("compressed:{}", archive_path.display());

        Ok(Self {
            instance_id,
            archive_path,
            inner_filename,
            compression_type,
        })
    }

    fn decompress(&self) -> Result<Vec<u8>, VfsError> {
        let file = File::open(&self.archive_path)?;
        let mut contents = Vec::new();

        match self.compression_type {
            CompressionType::Gzip => {
                let mut decoder = GzDecoder::new(file);
                decoder.read_to_end(&mut contents)?;
            }
            CompressionType::Bzip2 => {
                let mut decoder = BzDecoder::new(file);
                decoder.read_to_end(&mut contents)?;
            }
            CompressionType::Xz => {
                let mut decoder = XzDecoder::new(file);
                decoder.read_to_end(&mut contents)?;
            }
        }

        Ok(contents)
    }
}

impl Vfs for CompressedFileVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let path_str = path.to_string_lossy();
        if path_str.is_empty() || path_str == "." {
            // Root directory
            let file_meta = std::fs::metadata(&self.archive_path)?;
            return Ok(FileMetadata {
                size: 0,
                modified: file_meta.modified().unwrap_or(SystemTime::UNIX_EPOCH),
                is_dir: true,
                is_symlink: false,
            });
        }

        if path_str == self.inner_filename || path == Path::new(&self.inner_filename) {
            // Get decompressed size
            let contents = self.decompress()?;
            let file_meta = std::fs::metadata(&self.archive_path)?;

            return Ok(FileMetadata {
                size: contents.len() as u64,
                modified: file_meta.modified().unwrap_or(SystemTime::UNIX_EPOCH),
                is_dir: false,
                is_symlink: false,
            });
        }

        Err(VfsError::NotFound(path.display().to_string()))
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let path_str = path.to_string_lossy();
        if !path_str.is_empty() && path_str != "." {
            return Err(VfsError::NotADirectory(path.display().to_string()));
        }

        let file_meta = std::fs::metadata(&self.archive_path)?;
        let contents = self.decompress()?;

        Ok(vec![FileEntry {
            path: PathBuf::from(&self.inner_filename),
            size: contents.len() as u64,
            modified: file_meta.modified().unwrap_or(SystemTime::UNIX_EPOCH),
            is_dir: false,
        }])
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let path_str = path.to_string_lossy();
        if path_str != self.inner_filename && path != Path::new(&self.inner_filename) {
            return Err(VfsError::NotFound(path.display().to_string()));
        }

        let contents = self.decompress()?;
        Ok(Box::new(Cursor::new(contents)))
    }

    fn remove_file(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Compressed files are read-only".to_string()))
    }

    fn copy_file(&self, _src: &Path, _dest: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Compressed files are read-only".to_string()))
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities::read_only()
    }
}

/// Writable compressed file VFS
/// Maintains content in memory and compresses on flush
pub struct WritableCompressedFileVfs {
    instance_id: String,
    archive_path: PathBuf,
    inner_filename: String,
    compression_type: CompressionType,
    content: Arc<Mutex<Vec<u8>>>,
    modified: Arc<Mutex<bool>>,
}

impl WritableCompressedFileVfs {
    pub fn new(archive_path: PathBuf) -> Result<Self, VfsError> {
        let compression_type = CompressionType::from_path(&archive_path)
            .ok_or_else(|| VfsError::Unsupported("Unknown compression type".to_string()))?;

        let filename = archive_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();

        let inner_filename = filename
            .strip_suffix(compression_type.extension())
            .unwrap_or(&filename)
            .to_string();

        // Load existing content if archive exists
        let content = if archive_path.exists() {
            let file = File::open(&archive_path)?;
            let mut contents = Vec::new();

            match compression_type {
                CompressionType::Gzip => {
                    let mut decoder = GzDecoder::new(file);
                    decoder.read_to_end(&mut contents)?;
                }
                CompressionType::Bzip2 => {
                    let mut decoder = BzDecoder::new(file);
                    decoder.read_to_end(&mut contents)?;
                }
                CompressionType::Xz => {
                    let mut decoder = XzDecoder::new(file);
                    decoder.read_to_end(&mut contents)?;
                }
            }
            contents
        } else {
            Vec::new()
        };

        let instance_id = format!("compressed-rw:{}", archive_path.display());

        Ok(Self {
            instance_id,
            archive_path,
            inner_filename,
            compression_type,
            content: Arc::new(Mutex::new(content)),
            modified: Arc::new(Mutex::new(false)),
        })
    }

    pub fn create(archive_path: PathBuf) -> Result<Self, VfsError> {
        let compression_type = CompressionType::from_path(&archive_path)
            .ok_or_else(|| VfsError::Unsupported("Unknown compression type".to_string()))?;

        let filename = archive_path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();

        let inner_filename = filename
            .strip_suffix(compression_type.extension())
            .unwrap_or(&filename)
            .to_string();

        let instance_id = format!("compressed-rw:{}", archive_path.display());

        Ok(Self {
            instance_id,
            archive_path,
            inner_filename,
            compression_type,
            content: Arc::new(Mutex::new(Vec::new())),
            modified: Arc::new(Mutex::new(true)),
        })
    }

    fn mark_modified(&self) {
        if let Ok(mut modified) = self.modified.lock() {
            *modified = true;
        }
    }

    fn compress_and_write(&self) -> Result<(), VfsError> {
        let content = self.content.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock content")))?;

        let file = File::create(&self.archive_path)?;

        match self.compression_type {
            CompressionType::Gzip => {
                let mut encoder = GzEncoder::new(file, Compression::default());
                encoder.write_all(&content)?;
                encoder.finish()?;
            }
            CompressionType::Bzip2 => {
                let mut encoder = BzEncoder::new(file, bzip2::Compression::default());
                encoder.write_all(&content)?;
                encoder.finish()?;
            }
            CompressionType::Xz => {
                let mut encoder = XzEncoder::new(file, 6);
                encoder.write_all(&content)?;
                encoder.finish()?;
            }
        }

        Ok(())
    }
}

impl Vfs for WritableCompressedFileVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let path_str = path.to_string_lossy();
        if path_str.is_empty() || path_str == "." {
            return Ok(FileMetadata {
                size: 0,
                modified: SystemTime::now(),
                is_dir: true,
                is_symlink: false,
            });
        }

        if path_str == self.inner_filename || path == Path::new(&self.inner_filename) {
            let content = self.content.lock()
                .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock content")))?;

            return Ok(FileMetadata {
                size: content.len() as u64,
                modified: SystemTime::now(),
                is_dir: false,
                is_symlink: false,
            });
        }

        Err(VfsError::NotFound(path.display().to_string()))
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let path_str = path.to_string_lossy();
        if !path_str.is_empty() && path_str != "." {
            return Err(VfsError::NotADirectory(path.display().to_string()));
        }

        let content = self.content.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock content")))?;

        Ok(vec![FileEntry {
            path: PathBuf::from(&self.inner_filename),
            size: content.len() as u64,
            modified: SystemTime::now(),
            is_dir: false,
        }])
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let path_str = path.to_string_lossy();
        if path_str != self.inner_filename && path != Path::new(&self.inner_filename) {
            return Err(VfsError::NotFound(path.display().to_string()));
        }

        let content = self.content.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock content")))?;

        Ok(Box::new(Cursor::new(content.clone())))
    }

    fn remove_file(&self, _path: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Cannot remove the only file in a compressed archive".to_string()))
    }

    fn copy_file(&self, _src: &Path, _dest: &Path) -> Result<(), VfsError> {
        Err(VfsError::Unsupported("Copy not supported in single-file compressed archives".to_string()))
    }

    fn is_writable(&self) -> bool {
        true
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities {
            read: true,
            write: true,
            delete: false,
            rename: false,
            create_dir: false,
            set_mtime: false,
        }
    }

    fn create_file(&self, path: &Path) -> Result<Box<dyn Write + Send>, VfsError> {
        let path_str = path.to_string_lossy();
        if path_str != self.inner_filename && path != Path::new(&self.inner_filename) {
            return Err(VfsError::Unsupported("Can only write to the inner file".to_string()));
        }

        self.mark_modified();

        // Return a writer that updates the content
        let content = self.content.clone();
        let modified = self.modified.clone();
        Ok(Box::new(ContentWriter { content, modified }))
    }

    fn write_file(&self, path: &Path, new_content: &[u8]) -> Result<(), VfsError> {
        let path_str = path.to_string_lossy();
        if path_str != self.inner_filename && path != Path::new(&self.inner_filename) {
            return Err(VfsError::Unsupported("Can only write to the inner file".to_string()));
        }

        self.mark_modified();

        let mut content = self.content.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock content")))?;

        content.clear();
        content.extend_from_slice(new_content);

        Ok(())
    }

    fn flush(&self) -> Result<(), VfsError> {
        let modified = self.modified.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock modified flag")))?;

        if *modified {
            drop(modified);
            self.compress_and_write()?;

            if let Ok(mut modified) = self.modified.lock() {
                *modified = false;
            }
        }
        Ok(())
    }
}

/// Helper struct for writing content to WritableCompressedFileVfs
struct ContentWriter {
    content: Arc<Mutex<Vec<u8>>>,
    modified: Arc<Mutex<bool>>,
}

impl Write for ContentWriter {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        let mut content = self.content.lock()
            .map_err(|_| std::io::Error::new(std::io::ErrorKind::Other, "Failed to lock content"))?;
        content.extend_from_slice(buf);

        if let Ok(mut modified) = self.modified.lock() {
            *modified = true;
        }

        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

// ContentWriter needs Send for Box<dyn Write + Send>
unsafe impl Send for ContentWriter {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zip_vfs_creation() {
        let result = ZipVfs::new(PathBuf::from("/nonexistent.zip"));
        assert!(result.is_err());
    }

    #[test]
    fn test_tar_vfs_creation() {
        let result = TarVfs::new(PathBuf::from("/nonexistent.tar"));
        assert!(result.is_err());
    }

    #[test]
    fn test_sevenz_vfs_creation() {
        let result = SevenZVfs::new(PathBuf::from("/nonexistent.7z"));
        assert!(result.is_err());
    }

    #[test]
    fn test_rar_vfs_creation() {
        let result = RarVfs::new(PathBuf::from("/nonexistent.rar"));
        assert!(result.is_err());
    }

    #[test]
    fn test_writable_zip_vfs_create_and_flush() {
        let temp = tempfile::TempDir::new().unwrap();
        let archive_path = temp.path().join("test.zip");

        // Create a new writable ZIP
        let vfs = WritableZipVfs::create(archive_path.clone()).unwrap();

        // Write a file
        vfs.write_file(Path::new("hello.txt"), b"Hello, World!").unwrap();
        vfs.create_dir(Path::new("subdir")).unwrap();
        vfs.write_file(Path::new("subdir/nested.txt"), b"Nested content").unwrap();

        // Flush to create the archive
        vfs.flush().unwrap();

        // Verify the archive was created
        assert!(archive_path.exists());

        // Open with read-only VFS and verify contents
        let read_vfs = ZipVfs::new(archive_path).unwrap();
        let entries = read_vfs.read_dir(Path::new("")).unwrap();
        assert!(!entries.is_empty());
    }

    #[test]
    fn test_writable_tar_vfs_create_and_flush() {
        let temp = tempfile::TempDir::new().unwrap();
        let archive_path = temp.path().join("test.tar");

        // Create a new writable TAR
        let vfs = WritableTarVfs::create(archive_path.clone()).unwrap();

        // Write a file
        vfs.write_file(Path::new("test.txt"), b"TAR content").unwrap();

        // Flush to create the archive
        vfs.flush().unwrap();

        // Verify the archive was created
        assert!(archive_path.exists());

        // Open with read-only VFS and verify contents
        let read_vfs = TarVfs::new(archive_path).unwrap();
        let mut reader = read_vfs.open_file(Path::new("test.txt")).unwrap();
        let mut content = String::new();
        reader.read_to_string(&mut content).unwrap();
        assert_eq!(content, "TAR content");
    }

    #[test]
    fn test_writable_tar_gz_vfs() {
        let temp = tempfile::TempDir::new().unwrap();
        let archive_path = temp.path().join("test.tar.gz");

        // Create a new writable TAR.GZ
        let vfs = WritableTarVfs::create(archive_path.clone()).unwrap();
        vfs.write_file(Path::new("compressed.txt"), b"Compressed content").unwrap();
        vfs.flush().unwrap();

        assert!(archive_path.exists());

        // Verify it's gzip compressed
        let file = File::open(&archive_path).unwrap();
        let mut bytes = [0u8; 2];
        std::io::BufReader::new(file).read_exact(&mut bytes).unwrap();
        assert_eq!(bytes, [0x1f, 0x8b]); // Gzip magic number
    }

    #[test]
    fn test_compression_type_detection() {
        assert_eq!(CompressionType::from_path(Path::new("file.gz")), Some(CompressionType::Gzip));
        assert_eq!(CompressionType::from_path(Path::new("file.bz2")), Some(CompressionType::Bzip2));
        assert_eq!(CompressionType::from_path(Path::new("file.xz")), Some(CompressionType::Xz));

        // TAR archives should not be detected as compressed files
        assert_eq!(CompressionType::from_path(Path::new("file.tar.gz")), None);
        assert_eq!(CompressionType::from_path(Path::new("file.tar.bz2")), None);
        assert_eq!(CompressionType::from_path(Path::new("file.tar.xz")), None);

        // Unknown extensions
        assert_eq!(CompressionType::from_path(Path::new("file.txt")), None);
        assert_eq!(CompressionType::from_path(Path::new("file.zip")), None);
    }

    #[test]
    fn test_compressed_file_vfs_gzip() {
        let temp = tempfile::TempDir::new().unwrap();
        let archive_path = temp.path().join("test.txt.gz");

        // Create a gzip file
        let file = File::create(&archive_path).unwrap();
        let mut encoder = GzEncoder::new(file, Compression::default());
        encoder.write_all(b"Hello from gzip!").unwrap();
        encoder.finish().unwrap();

        // Open with CompressedFileVfs
        let vfs = CompressedFileVfs::new(archive_path).unwrap();

        // Check metadata
        let meta = vfs.metadata(Path::new("test.txt")).unwrap();
        assert!(!meta.is_dir);
        assert_eq!(meta.size, 16); // "Hello from gzip!" length

        // Read content
        let mut reader = vfs.open_file(Path::new("test.txt")).unwrap();
        let mut content = String::new();
        reader.read_to_string(&mut content).unwrap();
        assert_eq!(content, "Hello from gzip!");

        // List directory
        let entries = vfs.read_dir(Path::new("")).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].path, PathBuf::from("test.txt"));
    }

    #[test]
    fn test_writable_compressed_file_vfs() {
        let temp = tempfile::TempDir::new().unwrap();
        let archive_path = temp.path().join("output.txt.gz");

        // Create and write
        let vfs = WritableCompressedFileVfs::create(archive_path.clone()).unwrap();
        vfs.write_file(Path::new("output.txt"), b"New gzip content").unwrap();
        vfs.flush().unwrap();

        // Verify by reading back
        let read_vfs = CompressedFileVfs::new(archive_path).unwrap();
        let mut reader = read_vfs.open_file(Path::new("output.txt")).unwrap();
        let mut content = String::new();
        reader.read_to_string(&mut content).unwrap();
        assert_eq!(content, "New gzip content");
    }

    #[test]
    fn test_compressed_file_vfs_bzip2() {
        let temp = tempfile::TempDir::new().unwrap();
        let archive_path = temp.path().join("test.txt.bz2");

        // Create a bzip2 file
        let file = File::create(&archive_path).unwrap();
        let mut encoder = BzEncoder::new(file, bzip2::Compression::default());
        encoder.write_all(b"Hello from bzip2!").unwrap();
        encoder.finish().unwrap();

        // Open and verify
        let vfs = CompressedFileVfs::new(archive_path).unwrap();
        let mut reader = vfs.open_file(Path::new("test.txt")).unwrap();
        let mut content = String::new();
        reader.read_to_string(&mut content).unwrap();
        assert_eq!(content, "Hello from bzip2!");
    }

    #[test]
    fn test_compressed_file_vfs_xz() {
        let temp = tempfile::TempDir::new().unwrap();
        let archive_path = temp.path().join("test.txt.xz");

        // Create an xz file
        let file = File::create(&archive_path).unwrap();
        let mut encoder = XzEncoder::new(file, 6);
        encoder.write_all(b"Hello from xz!").unwrap();
        encoder.finish().unwrap();

        // Open and verify
        let vfs = CompressedFileVfs::new(archive_path).unwrap();
        let mut reader = vfs.open_file(Path::new("test.txt")).unwrap();
        let mut content = String::new();
        reader.read_to_string(&mut content).unwrap();
        assert_eq!(content, "Hello from xz!");
    }

    #[test]
    fn test_vfs_capabilities() {
        let temp = tempfile::TempDir::new().unwrap();

        // Read-only VFS should have read-only capabilities
        let zip_path = temp.path().join("test.zip");
        // Create a minimal zip
        {
            let file = File::create(&zip_path).unwrap();
            let mut zip = ZipWriter::new(file);
            zip.finish().unwrap();
        }

        let vfs = ZipVfs::new(zip_path).unwrap();
        let caps = vfs.capabilities();
        assert!(caps.read);
        assert!(!caps.write);

        // Writable VFS should have full capabilities
        let writable_zip_path = temp.path().join("writable.zip");
        let writable_vfs = WritableZipVfs::create(writable_zip_path).unwrap();
        let caps = writable_vfs.capabilities();
        assert!(caps.read);
        assert!(caps.write);
        assert!(caps.delete);
        assert!(caps.rename);
        assert!(caps.create_dir);
    }

    #[test]
    fn test_is_gzip_archive_detection() {
        assert!(is_gzip_archive(Path::new("file.tar.gz")));
        assert!(is_gzip_archive(Path::new("file.tgz")));
        assert!(!is_gzip_archive(Path::new("file.tar")));
        assert!(!is_gzip_archive(Path::new("file.gz")));
        assert!(!is_gzip_archive(Path::new("file.tar.bz2")));
    }
}
