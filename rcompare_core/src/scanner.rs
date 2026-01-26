use rcompare_common::{AppConfig, FileEntry, RCompareError, Vfs};
use std::path::Path;
use jwalk::WalkDir;
use ignore::gitignore::{Gitignore, GitignoreBuilder};
use std::sync::atomic::{AtomicBool, Ordering};
use tracing::debug;

/// Parallel folder scanner using jwalk
pub struct FolderScanner {
    config: AppConfig,
    gitignore: Option<Gitignore>,
    custom_ignore: Option<Gitignore>,
}

impl FolderScanner {
    pub fn new(config: AppConfig) -> Self {
        let custom_ignore = Self::build_custom_ignore(&config);
        Self {
            config,
            gitignore: None,
            custom_ignore,
        }
    }

    /// Build a Gitignore from custom ignore patterns in config
    fn build_custom_ignore(config: &AppConfig) -> Option<Gitignore> {
        if config.ignore_patterns.is_empty() {
            return None;
        }

        let mut builder = GitignoreBuilder::new("");
        for pattern in &config.ignore_patterns {
            if let Err(err) = builder.add_line(None, pattern) {
                debug!("Failed to add ignore pattern '{}': {}", pattern, err);
            } else {
                debug!("Added custom ignore pattern: {}", pattern);
            }
        }

        match builder.build() {
            Ok(ignore) => {
                debug!("Built custom ignore with {} patterns", config.ignore_patterns.len());
                Some(ignore)
            }
            Err(e) => {
                debug!("Failed to build custom ignore: {}", e);
                None
            }
        }
    }

    /// Load .gitignore patterns from a directory (including nested .gitignore files)
    pub fn load_gitignore(&mut self, root: &Path) -> Result<(), RCompareError> {
        let mut builder = GitignoreBuilder::new(root);
        let mut found_any = false;

        // Recursively find all .gitignore files in the directory tree
        for entry in WalkDir::new(root) {
            if let Ok(entry) = entry {
                let path = entry.path();
                if path.file_name() == Some(std::ffi::OsStr::new(".gitignore")) {
                    if let Some(e) = builder.add(&path) {
                        debug!("Failed to add .gitignore from {:?}: {}", path, e);
                    } else {
                        debug!("Added .gitignore from {:?}", path);
                        found_any = true;
                    }
                }
            }
        }

        if found_any {
            self.gitignore = Some(builder.build()
                .map_err(|e| RCompareError::Config(format!("Failed to build gitignore: {}", e)))?);
            debug!("Built gitignore with nested .gitignore files");
        }

        Ok(())
    }

    /// Scan a directory and return all files and subdirectories
    pub fn scan(&self, root: &Path) -> Result<Vec<FileEntry>, RCompareError> {
        self.scan_with_cancel(root, None)
    }

    /// Scan a directory and return all files and subdirectories, with cancellation
    pub fn scan_with_cancel(
        &self,
        root: &Path,
        cancel: Option<&AtomicBool>,
    ) -> Result<Vec<FileEntry>, RCompareError> {
        let mut entries = Vec::new();

        let walker = WalkDir::new(root)
            .follow_links(self.config.follow_symlinks)
            .skip_hidden(false);

        for entry in walker {
            if cancel.map_or(false, |flag| flag.load(Ordering::Relaxed)) {
                return Err(RCompareError::Comparison("Scan cancelled".to_string()));
            }

            let entry = entry.map_err(|e| RCompareError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Walk error: {}", e)
            )))?;

            let path = entry.path();
            let relative_path = path.strip_prefix(root)
                .map_err(|e| RCompareError::Path(e.to_string()))?
                .to_path_buf();

            // Skip the synthetic root entry (empty path)
            if relative_path.as_os_str().is_empty() {
                continue;
            }

            let is_dir = entry.file_type().is_dir();

            // Skip if matches ignore patterns (check full path and all parent directories)
            if self.should_ignore_with_parents(&relative_path, is_dir) {
                continue;
            }

            // Skip if matches gitignore (check full path and all parent directories)
            if let Some(ref gitignore) = self.gitignore {
                if self.gitignore_matches_with_parents(gitignore, &relative_path, is_dir) {
                    continue;
                }
            }

            let metadata = entry.metadata()
                .map_err(|e| RCompareError::Io(std::io::Error::new(
                    std::io::ErrorKind::Other,
                    format!("Metadata error: {}", e)
                )))?;

            entries.push(FileEntry {
                path: relative_path,
                size: metadata.len(),
                modified: metadata.modified()
                    .unwrap_or(std::time::SystemTime::UNIX_EPOCH),
                is_dir: metadata.is_dir(),
            });
        }

        debug!("Scanned {} entries from {:?}", entries.len(), root);
        Ok(entries)
    }

    /// Scan a VFS and return all files and subdirectories
    pub fn scan_vfs(&self, vfs: &dyn Vfs, root: &Path) -> Result<Vec<FileEntry>, RCompareError> {
        self.scan_vfs_with_cancel(vfs, root, None)
    }

    /// Scan a VFS and return all files and subdirectories, with cancellation
    pub fn scan_vfs_with_cancel(
        &self,
        vfs: &dyn Vfs,
        root: &Path,
        cancel: Option<&AtomicBool>,
    ) -> Result<Vec<FileEntry>, RCompareError> {
        let mut entries = Vec::new();
        self.scan_vfs_recursive(vfs, root, root, &mut entries, cancel)?;
        Ok(entries)
    }

    fn scan_vfs_recursive(
        &self,
        vfs: &dyn Vfs,
        root: &Path,
        current: &Path,
        entries: &mut Vec<FileEntry>,
        cancel: Option<&AtomicBool>,
    ) -> Result<(), RCompareError> {
        if cancel.map_or(false, |flag| flag.load(Ordering::Relaxed)) {
            return Err(RCompareError::Comparison("Scan cancelled".to_string()));
        }

        let dir_entries = vfs.read_dir(current)
            .map_err(|e| RCompareError::Vfs(e.to_string()))?;

        for entry in dir_entries {
            if cancel.map_or(false, |flag| flag.load(Ordering::Relaxed)) {
                return Err(RCompareError::Comparison("Scan cancelled".to_string()));
            }

            let vfs_path = entry.path.clone();
            let relative_path = vfs_path.strip_prefix(root)
                .unwrap_or(&vfs_path)
                .to_path_buf();

            // Skip the synthetic root entry (empty path)
            if relative_path.as_os_str().is_empty() {
                continue;
            }

            if self.should_ignore_with_parents(&relative_path, entry.is_dir) {
                continue;
            }

            if let Some(ref gitignore) = self.gitignore {
                if self.gitignore_matches_with_parents(gitignore, &relative_path, entry.is_dir) {
                    continue;
                }
            }

            entries.push(FileEntry {
                path: relative_path,
                size: entry.size,
                modified: entry.modified,
                is_dir: entry.is_dir,
            });

            if entry.is_dir {
                self.scan_vfs_recursive(vfs, root, &vfs_path, entries, cancel)?;
            }
        }

        Ok(())
    }

    /// Check if a path or any of its parent directories should be ignored
    fn should_ignore_with_parents(&self, path: &Path, is_dir: bool) -> bool {
        if let Some(ref custom_ignore) = self.custom_ignore {
            // Check the path itself
            if custom_ignore.matched(path, is_dir).is_ignore() {
                return true;
            }

            // Check all parent directories
            let mut current = path;
            while let Some(parent) = current.parent() {
                if !parent.as_os_str().is_empty() {
                    if custom_ignore.matched(parent, true).is_ignore() {
                        return true;
                    }
                }
                current = parent;
            }
        }
        false
    }

    /// Check if a path or any of its parent directories match gitignore
    fn gitignore_matches_with_parents(&self, gitignore: &Gitignore, path: &Path, is_dir: bool) -> bool {
        // Check the path itself
        if gitignore.matched(path, is_dir).is_ignore() {
            return true;
        }

        // Check all parent directories
        let mut current = path;
        while let Some(parent) = current.parent() {
            if !parent.as_os_str().is_empty() {
                if gitignore.matched(parent, true).is_ignore() {
                    return true;
                }
            }
            current = parent;
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_scanner_basic() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("file1.txt"), b"test").unwrap();
        fs::write(temp.path().join("file2.txt"), b"test").unwrap();
        fs::create_dir(temp.path().join("subdir")).unwrap();
        fs::write(temp.path().join("subdir/file3.txt"), b"test").unwrap();

        let config = AppConfig::default();
        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Should have exactly 4 entries: file1.txt, file2.txt, subdir, subdir/file3.txt
        // Root directory itself should NOT be included
        assert_eq!(entries.len(), 4, "Expected 4 entries, got {}", entries.len());

        // Verify no entry has an empty path (which would indicate root directory)
        for entry in &entries {
            assert!(!entry.path.as_os_str().is_empty(),
                    "Found entry with empty path (root directory should be excluded)");
        }
    }

    #[test]
    fn test_scanner_ignore_patterns() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("file1.txt"), b"test").unwrap();
        fs::write(temp.path().join("file2.o"), b"test").unwrap();

        let mut config = AppConfig::default();
        config.ignore_patterns = vec!["*.o".to_string()];

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        assert!(entries.iter().all(|e| !e.path.to_string_lossy().ends_with(".o")));
    }

    #[test]
    fn test_scanner_gitignore_style_patterns() {
        let temp = TempDir::new().unwrap();

        // Create test structure
        fs::write(temp.path().join("root.txt"), b"test").unwrap();
        fs::write(temp.path().join("root.log"), b"test").unwrap();
        fs::create_dir(temp.path().join("subdir")).unwrap();
        fs::write(temp.path().join("subdir/nested.txt"), b"test").unwrap();
        fs::write(temp.path().join("subdir/nested.log"), b"test").unwrap();
        fs::create_dir(temp.path().join("build")).unwrap();
        fs::write(temp.path().join("build/output.txt"), b"test").unwrap();

        let mut config = AppConfig::default();
        config.ignore_patterns = vec![
            "*.log".to_string(),     // Ignore all .log files at any depth
            "build/".to_string(),    // Ignore build directory
        ];

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Should not contain any .log files
        assert!(entries.iter().all(|e| !e.path.to_string_lossy().ends_with(".log")),
                "Found .log file that should be ignored");

        // Should not contain the build directory or its contents
        assert!(entries.iter().all(|e| !e.path.starts_with("build")),
                "Found file in build directory that should be ignored");

        // Should contain .txt files outside build directory
        assert!(entries.iter().any(|e| e.path.to_string_lossy().ends_with("root.txt")),
                "Missing root.txt");
        assert!(entries.iter().any(|e| e.path.to_string_lossy().ends_with("nested.txt")),
                "Missing nested.txt");
    }

    #[test]
    fn test_scanner_root_relative_patterns() {
        let temp = TempDir::new().unwrap();

        // Create test structure
        fs::write(temp.path().join("config.toml"), b"test").unwrap();
        fs::create_dir(temp.path().join("subdir")).unwrap();
        fs::write(temp.path().join("subdir/config.toml"), b"test").unwrap();

        let mut config = AppConfig::default();
        config.ignore_patterns = vec![
            "/config.toml".to_string(),  // Ignore only in root
        ];

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Should not contain root config.toml
        assert!(entries.iter().all(|e| e.path.to_str() != Some("config.toml")),
                "Found root config.toml that should be ignored");

        // Should contain nested config.toml
        assert!(entries.iter().any(|e| e.path.to_string_lossy().contains("subdir")
                                    && e.path.to_string_lossy().ends_with("config.toml")),
                "Missing subdir/config.toml");
    }

    #[test]
    fn test_scanner_directory_only_patterns() {
        let temp = TempDir::new().unwrap();

        // Create test structure
        fs::create_dir(temp.path().join("temp")).unwrap();
        fs::write(temp.path().join("temp/file.txt"), b"test").unwrap();
        fs::write(temp.path().join("temp.txt"), b"test").unwrap();  // File named "temp.txt"

        let mut config = AppConfig::default();
        config.ignore_patterns = vec![
            "temp/".to_string(),  // Ignore only directories named "temp"
        ];

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Should not contain temp directory or its contents
        assert!(entries.iter().all(|e| !e.path.starts_with("temp") || e.path.extension().is_some()),
                "Found temp directory that should be ignored");

        // Should contain temp.txt file
        assert!(entries.iter().any(|e| e.path.to_str() == Some("temp.txt")),
                "Missing temp.txt file");
    }

    #[test]
    fn test_scanner_no_root_entry() {
        let temp = TempDir::new().unwrap();

        // Create a simple structure
        fs::write(temp.path().join("test.txt"), b"content").unwrap();
        fs::create_dir(temp.path().join("subdir")).unwrap();

        let config = AppConfig::default();
        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Verify no empty paths (root directory)
        for entry in &entries {
            assert!(!entry.path.as_os_str().is_empty(),
                    "Scanner included root directory entry with empty path");
            assert!(entry.path != std::path::PathBuf::from(""),
                    "Scanner included root directory with empty PathBuf");
        }

        // Should have exactly 2 entries: test.txt and subdir
        assert_eq!(entries.len(), 2,
                   "Expected 2 entries (excluding root), got {}", entries.len());
    }
}
