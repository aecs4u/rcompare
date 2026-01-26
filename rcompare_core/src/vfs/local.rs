use rcompare_common::{FileEntry, FileMetadata, Vfs, VfsCapabilities, VfsError};
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

/// Local filesystem VFS implementation
pub struct LocalVfs {
    instance_id: String,
    root: PathBuf,
}

impl LocalVfs {
    pub fn new(root: PathBuf) -> Self {
        let instance_id = format!("local:{}", root.display());
        Self { instance_id, root }
    }
}

impl Vfs for LocalVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let full_path = self.root.join(path);
        let meta = fs::metadata(&full_path)?;

        Ok(FileMetadata {
            size: meta.len(),
            modified: meta.modified().unwrap_or(SystemTime::UNIX_EPOCH),
            is_dir: meta.is_dir(),
            is_symlink: meta.is_symlink(),
        })
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let full_path = self.root.join(path);

        if !full_path.is_dir() {
            return Err(VfsError::NotADirectory(full_path.display().to_string()));
        }

        let entries = fs::read_dir(&full_path)?
            .filter_map(|entry| {
                let entry = entry.ok()?;
                let meta = entry.metadata().ok()?;
                let rel_path = entry.path().strip_prefix(&self.root).ok()?.to_path_buf();

                Some(FileEntry {
                    path: rel_path,
                    size: meta.len(),
                    modified: meta.modified().unwrap_or(SystemTime::UNIX_EPOCH),
                    is_dir: meta.is_dir(),
                })
            })
            .collect();

        Ok(entries)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let full_path = self.root.join(path);

        if !full_path.is_file() {
            return Err(VfsError::NotAFile(full_path.display().to_string()));
        }

        let file = fs::File::open(&full_path)?;
        Ok(Box::new(file))
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        let full_path = self.root.join(path);
        fs::remove_file(&full_path)?;
        Ok(())
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        let src_path = self.root.join(src);
        let dest_path = self.root.join(dest);

        fs::copy(&src_path, &dest_path)?;
        Ok(())
    }

    fn is_writable(&self) -> bool {
        true
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities::full()
    }

    fn create_file(&self, path: &Path) -> Result<Box<dyn Write + Send>, VfsError> {
        let full_path = self.root.join(path);

        // Ensure parent directory exists
        if let Some(parent) = full_path.parent() {
            if !parent.exists() {
                fs::create_dir_all(parent)?;
            }
        }

        let file = fs::File::create(&full_path)?;
        Ok(Box::new(file))
    }

    fn create_dir(&self, path: &Path) -> Result<(), VfsError> {
        let full_path = self.root.join(path);
        fs::create_dir(&full_path)?;
        Ok(())
    }

    fn create_dir_all(&self, path: &Path) -> Result<(), VfsError> {
        let full_path = self.root.join(path);
        fs::create_dir_all(&full_path)?;
        Ok(())
    }

    fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError> {
        let from_path = self.root.join(from);
        let to_path = self.root.join(to);
        fs::rename(&from_path, &to_path)?;
        Ok(())
    }

    fn set_mtime(&self, path: &Path, mtime: SystemTime) -> Result<(), VfsError> {
        let full_path = self.root.join(path);
        let duration = mtime
            .duration_since(SystemTime::UNIX_EPOCH)
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidData, e)))?;
        let filetime = filetime::FileTime::from_unix_time(duration.as_secs() as i64, 0);
        filetime::set_file_mtime(&full_path, filetime)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_local_vfs_metadata() {
        let temp = TempDir::new().unwrap();
        let test_file = temp.path().join("test.txt");
        fs::write(&test_file, b"hello").unwrap();

        let vfs = LocalVfs::new(temp.path().to_path_buf());
        let meta = vfs.metadata(Path::new("test.txt")).unwrap();

        assert_eq!(meta.size, 5);
        assert!(!meta.is_dir);
    }

    #[test]
    fn test_local_vfs_read_dir() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("file1.txt"), b"a").unwrap();
        fs::write(temp.path().join("file2.txt"), b"b").unwrap();

        let vfs = LocalVfs::new(temp.path().to_path_buf());
        let entries = vfs.read_dir(Path::new("")).unwrap();

        assert_eq!(entries.len(), 2);
    }

    #[test]
    fn test_local_vfs_is_writable() {
        let temp = TempDir::new().unwrap();
        let vfs = LocalVfs::new(temp.path().to_path_buf());
        assert!(vfs.is_writable());
    }

    #[test]
    fn test_local_vfs_capabilities() {
        let temp = TempDir::new().unwrap();
        let vfs = LocalVfs::new(temp.path().to_path_buf());
        let caps = vfs.capabilities();
        assert!(caps.read);
        assert!(caps.write);
        assert!(caps.delete);
        assert!(caps.rename);
        assert!(caps.create_dir);
        assert!(caps.set_mtime);
    }

    #[test]
    fn test_local_vfs_create_file() {
        let temp = TempDir::new().unwrap();
        let vfs = LocalVfs::new(temp.path().to_path_buf());

        let mut writer = vfs.create_file(Path::new("new_file.txt")).unwrap();
        writer.write_all(b"test content").unwrap();
        drop(writer);

        // Verify file was created
        let content = fs::read_to_string(temp.path().join("new_file.txt")).unwrap();
        assert_eq!(content, "test content");
    }

    #[test]
    fn test_local_vfs_create_file_nested() {
        let temp = TempDir::new().unwrap();
        let vfs = LocalVfs::new(temp.path().to_path_buf());

        // Create file in nested directory that doesn't exist yet
        let mut writer = vfs.create_file(Path::new("subdir/deep/file.txt")).unwrap();
        writer.write_all(b"nested content").unwrap();
        drop(writer);

        // Verify file was created
        let content = fs::read_to_string(temp.path().join("subdir/deep/file.txt")).unwrap();
        assert_eq!(content, "nested content");
    }

    #[test]
    fn test_local_vfs_create_dir() {
        let temp = TempDir::new().unwrap();
        let vfs = LocalVfs::new(temp.path().to_path_buf());

        vfs.create_dir(Path::new("new_dir")).unwrap();
        assert!(temp.path().join("new_dir").is_dir());
    }

    #[test]
    fn test_local_vfs_create_dir_all() {
        let temp = TempDir::new().unwrap();
        let vfs = LocalVfs::new(temp.path().to_path_buf());

        vfs.create_dir_all(Path::new("a/b/c/d")).unwrap();
        assert!(temp.path().join("a/b/c/d").is_dir());
    }

    #[test]
    fn test_local_vfs_rename() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("old.txt"), b"content").unwrap();

        let vfs = LocalVfs::new(temp.path().to_path_buf());
        vfs.rename(Path::new("old.txt"), Path::new("new.txt")).unwrap();

        assert!(!temp.path().join("old.txt").exists());
        assert!(temp.path().join("new.txt").exists());
    }

    #[test]
    fn test_local_vfs_set_mtime() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("test.txt"), b"content").unwrap();

        let vfs = LocalVfs::new(temp.path().to_path_buf());

        // Set mtime to a specific time (2020-01-01 00:00:00 UTC)
        let target_time = SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(1577836800);
        vfs.set_mtime(Path::new("test.txt"), target_time).unwrap();

        // Verify mtime was set
        let meta = fs::metadata(temp.path().join("test.txt")).unwrap();
        let mtime = meta.modified().unwrap();
        let diff = mtime.duration_since(target_time).unwrap_or_default();
        assert!(diff.as_secs() < 2); // Allow small tolerance
    }

    #[test]
    fn test_local_vfs_write_file() {
        let temp = TempDir::new().unwrap();
        let vfs = LocalVfs::new(temp.path().to_path_buf());

        vfs.write_file(Path::new("written.txt"), b"direct write").unwrap();

        let content = fs::read_to_string(temp.path().join("written.txt")).unwrap();
        assert_eq!(content, "direct write");
    }

    #[test]
    fn test_local_vfs_open_and_read() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("readable.txt"), b"read me").unwrap();

        let vfs = LocalVfs::new(temp.path().to_path_buf());
        let mut reader = vfs.open_file(Path::new("readable.txt")).unwrap();

        let mut content = String::new();
        reader.read_to_string(&mut content).unwrap();
        assert_eq!(content, "read me");
    }

    #[test]
    fn test_local_vfs_remove_file() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("to_delete.txt"), b"delete me").unwrap();
        assert!(temp.path().join("to_delete.txt").exists());

        let vfs = LocalVfs::new(temp.path().to_path_buf());
        vfs.remove_file(Path::new("to_delete.txt")).unwrap();

        assert!(!temp.path().join("to_delete.txt").exists());
    }

    #[test]
    fn test_local_vfs_copy_file() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("source.txt"), b"copy me").unwrap();

        let vfs = LocalVfs::new(temp.path().to_path_buf());
        vfs.copy_file(Path::new("source.txt"), Path::new("dest.txt")).unwrap();

        assert!(temp.path().join("source.txt").exists());
        assert!(temp.path().join("dest.txt").exists());
        let content = fs::read_to_string(temp.path().join("dest.txt")).unwrap();
        assert_eq!(content, "copy me");
    }
}
