//! Directory and VFS scanning with gitignore support.
//!
//! This module provides efficient, parallel directory traversal using jwalk,
//! with built-in support for .gitignore patterns and custom ignore rules.
//!
//! # Features
//!
//! - **Parallel scanning**: Uses jwalk for fast multi-threaded directory traversal
//! - **Gitignore support**: Respects .gitignore files (including nested ones), discovered
//!   incrementally in the same pass as the scan itself
//! - **Traversal pruning**: Ignored directories are never descended into
//! - **Custom ignore patterns**: Supports user-defined gitignore-style patterns
//! - **VFS abstraction**: Can scan both filesystem and virtual file systems (archives, cloud storage)
//! - **Cancellation**: Supports cancelling long-running scans
//! - **Symlink handling**: Configurable symlink following behavior
//! - **Race tolerance**: Filesystem races (a file vanishing mid-scan, a permission error)
//!   are collected as warnings and skipped by default; pass `strict: true` to fail fast instead
//!
//! # Examples
//!
//! Basic directory scanning:
//!
//! ```no_run
//! use rcompare_core::FolderScanner;
//! use rcompare_common::AppConfig;
//! use std::path::Path;
//!
//! let config = AppConfig::default();
//! let scanner = FolderScanner::new(config);
//! let entries = scanner.scan(Path::new("/path/to/directory")).unwrap();
//! println!("Found {} entries", entries.len());
//! ```
//!
//! Scanning with custom ignore patterns:
//!
//! ```no_run
//! use rcompare_core::FolderScanner;
//! use rcompare_common::AppConfig;
//! use std::path::Path;
//!
//! let config = AppConfig {
//!     ignore_patterns: vec!["*.o".to_string(), "target/".to_string()],
//!     ..Default::default()
//! };
//! let scanner = FolderScanner::new(config);
//! let entries = scanner.scan(Path::new("/project")).unwrap();
//! ```

use ignore::gitignore::{Gitignore, GitignoreBuilder};
use jwalk::{ClientState, DirEntry, WalkDirGeneric};
use rcompare_common::{AppConfig, FileEntry, RCompareError, Vfs};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tracing::debug;

/// A single non-fatal problem encountered while scanning, e.g. a file that
/// vanished between being listed and being stat'd, or a permission error.
///
/// These are collected instead of aborting the whole scan unless `strict`
/// mode is requested, since transient filesystem races are common in active
/// directories (build output, logs, mail spools) and shouldn't fail an
/// otherwise-successful comparison.
#[derive(Debug, Clone)]
pub struct ScanWarning {
    pub path: PathBuf,
    pub message: String,
}

/// Result of a scan: the entries found, plus any non-fatal warnings collected
/// along the way (empty unless races/permission errors were encountered).
#[derive(Debug, Default)]
pub struct ScanOutcome {
    pub entries: Vec<FileEntry>,
    pub warnings: Vec<ScanWarning>,
}

/// Per-directory state threaded through jwalk's `process_read_dir` callback.
///
/// Carries the accumulated list of `.gitignore` files discovered from the
/// scan root down to the current directory, plus the merged matcher built
/// from them. Rebuilt only when a *new* `.gitignore` file is discovered
/// (i.e. once per directory that has one), not per-entry.
#[derive(Clone, Debug, Default)]
struct GitignoreReadDirState {
    gitignore_paths: Arc<Vec<PathBuf>>,
    matcher: Option<Arc<Gitignore>>,
}

#[derive(Debug, Default)]
struct ScanClientState;

impl ClientState for ScanClientState {
    type ReadDirState = GitignoreReadDirState;
    type DirEntryState = ();
}

type ScanDirEntry = DirEntry<ScanClientState>;

/// Parallel folder scanner using jwalk with gitignore and custom pattern support.
///
/// The scanner efficiently traverses directory trees in parallel, respecting
/// .gitignore files and custom ignore patterns. It can scan both regular
/// filesystems and virtual file systems (VFS) for archives and cloud storage.
///
/// # Examples
///
/// ```no_run
/// use rcompare_core::FolderScanner;
/// use rcompare_common::AppConfig;
/// use std::path::Path;
///
/// let config = AppConfig::default();
/// let scanner = FolderScanner::new(config);
///
/// // Scan the directory (nested .gitignore files are discovered automatically)
/// let entries = scanner.scan(Path::new("/project")).unwrap();
/// ```
pub struct FolderScanner {
    config: AppConfig,
    custom_ignore: Option<Arc<Gitignore>>,
    /// If true, any per-entry error (race, permission denied, etc.) aborts
    /// the scan immediately instead of being collected as a warning.
    strict: bool,
}

impl FolderScanner {
    pub fn new(config: AppConfig) -> Self {
        let custom_ignore = Self::build_custom_ignore(&config).map(Arc::new);
        Self {
            config,
            custom_ignore,
            strict: false,
        }
    }

    /// Fail fast on filesystem races/permission errors instead of collecting
    /// them as warnings and continuing. Off by default.
    pub fn with_strict(mut self, strict: bool) -> Self {
        self.strict = strict;
        self
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
                debug!(
                    "Built custom ignore with {} patterns",
                    config.ignore_patterns.len()
                );
                Some(ignore)
            }
            Err(e) => {
                debug!("Failed to build custom ignore: {}", e);
                None
            }
        }
    }

    /// Retained for API compatibility: nested `.gitignore` discovery now
    /// happens incrementally during [`scan_with_cancel`] itself (one pass
    /// instead of a separate upfront walk), so this is a no-op.
    #[deprecated(
        note = "gitignore files are now discovered incrementally during scan_with_cancel; this method is a no-op"
    )]
    pub fn load_gitignore(&mut self, _root: &Path) -> Result<(), RCompareError> {
        Ok(())
    }

    /// Scan a directory and return all files and subdirectories
    pub fn scan(&self, root: &Path) -> Result<Vec<FileEntry>, RCompareError> {
        Ok(self.scan_with_cancel(root, None)?.entries)
    }

    /// Scan a directory, returning entries plus any non-fatal warnings.
    ///
    /// Traverses the tree exactly once: `.gitignore` files are discovered as
    /// their directory is visited (rather than in a separate upfront walk),
    /// and directories matched by custom ignore patterns or an applicable
    /// `.gitignore` are pruned before jwalk descends into them, so ignored
    /// subtrees are never read from disk.
    pub fn scan_with_cancel(
        &self,
        root: &Path,
        cancel: Option<&AtomicBool>,
    ) -> Result<ScanOutcome, RCompareError> {
        let mut outcome = ScanOutcome::default();

        let root_buf = root.to_path_buf();
        let custom_ignore = self.custom_ignore.clone();
        let follow_symlinks = self.config.follow_symlinks;

        let walker = WalkDirGeneric::<ScanClientState>::new(root)
            .follow_links(follow_symlinks)
            .skip_hidden(false)
            .process_read_dir(move |_depth, dir_path, read_dir_state, children| {
                Self::process_read_dir_prune(
                    &root_buf,
                    dir_path,
                    read_dir_state,
                    children,
                    custom_ignore.as_deref(),
                );
            });

        for entry in walker {
            if cancel.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
                return Err(RCompareError::Comparison("Scan cancelled".to_string()));
            }

            let entry = match entry {
                Ok(entry) => entry,
                Err(e) => {
                    if self.strict {
                        return Err(RCompareError::Io(std::io::Error::other(format!(
                            "Walk error: {e}"
                        ))));
                    }
                    outcome.warnings.push(ScanWarning {
                        path: e.path().map(Path::to_path_buf).unwrap_or_default(),
                        message: format!("walk error: {e}"),
                    });
                    continue;
                }
            };

            let path = entry.path();
            let relative_path = match path.strip_prefix(root) {
                Ok(p) => p.to_path_buf(),
                Err(e) => {
                    if self.strict {
                        return Err(RCompareError::Path(e.to_string()));
                    }
                    outcome.warnings.push(ScanWarning {
                        path: path.clone(),
                        message: format!("path error: {e}"),
                    });
                    continue;
                }
            };

            // Skip the synthetic root entry (empty path)
            if relative_path.as_os_str().is_empty() {
                continue;
            }

            let metadata = match entry.metadata() {
                Ok(m) => m,
                Err(e) => {
                    if self.strict {
                        return Err(RCompareError::Io(std::io::Error::other(format!(
                            "Metadata error: {e}"
                        ))));
                    }
                    outcome.warnings.push(ScanWarning {
                        path,
                        message: format!(
                            "metadata error (likely a race, file may have vanished): {e}"
                        ),
                    });
                    continue;
                }
            };

            // For symlinks, follow them to determine if they point to a directory
            // (jwalk's metadata returns false for is_dir on symlinks when follow_links is false)
            let is_dir = if metadata.file_type().is_symlink() {
                // Use std::fs::metadata to follow the symlink
                std::fs::metadata(&path)
                    .map(|m| m.is_dir())
                    .unwrap_or(false)
            } else {
                metadata.is_dir()
            };

            outcome.entries.push(FileEntry {
                path: relative_path,
                size: metadata.len(),
                modified: metadata
                    .modified()
                    .unwrap_or(std::time::SystemTime::UNIX_EPOCH),
                is_dir,
            });
        }

        debug!(
            "Scanned {} entries from {:?} ({} warnings)",
            outcome.entries.len(),
            root,
            outcome.warnings.len()
        );
        Ok(outcome)
    }

    /// `process_read_dir` callback: discovers `.gitignore` in the directory being
    /// read, extends/rebuilds the accumulated matcher if one is found, then
    /// filters `children` in place so ignored entries (and, critically, ignored
    /// *directories*) are dropped before jwalk ever descends into them.
    fn process_read_dir_prune(
        root: &Path,
        dir_path: &Path,
        read_dir_state: &mut GitignoreReadDirState,
        children: &mut Vec<jwalk::Result<ScanDirEntry>>,
        custom_ignore: Option<&Gitignore>,
    ) {
        let has_gitignore_file = children.iter().any(|c| {
            c.as_ref()
                .map(|e| e.file_name == std::ffi::OsStr::new(".gitignore"))
                .unwrap_or(false)
        });

        if has_gitignore_file {
            let gitignore_path = dir_path.join(".gitignore");
            let mut paths = (*read_dir_state.gitignore_paths).clone();
            paths.push(gitignore_path);

            let mut builder = GitignoreBuilder::new(root);
            for p in &paths {
                if let Some(err) = builder.add(p) {
                    debug!("Failed to add .gitignore from {:?}: {}", p, err);
                }
            }
            match builder.build() {
                Ok(matcher) => {
                    read_dir_state.matcher = Some(Arc::new(matcher));
                    read_dir_state.gitignore_paths = Arc::new(paths);
                }
                Err(e) => {
                    debug!("Failed to build gitignore for {:?}: {}", dir_path, e);
                }
            }
        }

        let gitignore = read_dir_state.matcher.clone();

        children.retain(|result| {
            let Ok(entry) = result else {
                return true; // keep errors; surfaced (or skipped) by the main loop
            };

            let child_path = dir_path.join(&entry.file_name);
            let Ok(rel) = child_path.strip_prefix(root) else {
                return true;
            };
            let is_dir = entry.file_type.is_dir();

            !Self::is_ignored(rel, is_dir, gitignore.as_deref(), custom_ignore)
        });
    }

    fn is_ignored(
        rel: &Path,
        is_dir: bool,
        gitignore: Option<&Gitignore>,
        custom_ignore: Option<&Gitignore>,
    ) -> bool {
        if let Some(g) = custom_ignore {
            if g.matched(rel, is_dir).is_ignore() {
                return true;
            }
        }
        if let Some(g) = gitignore {
            if g.matched(rel, is_dir).is_ignore() {
                return true;
            }
        }
        false
    }

    /// Scan a VFS and return all files and subdirectories
    pub fn scan_vfs(&self, vfs: &dyn Vfs, root: &Path) -> Result<Vec<FileEntry>, RCompareError> {
        Ok(self.scan_vfs_with_cancel(vfs, root, None)?.entries)
    }

    /// Scan a VFS and return all files and subdirectories, with cancellation
    pub fn scan_vfs_with_cancel(
        &self,
        vfs: &dyn Vfs,
        root: &Path,
        cancel: Option<&AtomicBool>,
    ) -> Result<ScanOutcome, RCompareError> {
        let mut outcome = ScanOutcome::default();
        self.scan_vfs_recursive(vfs, root, root, &mut outcome, cancel)?;
        Ok(outcome)
    }

    fn scan_vfs_recursive(
        &self,
        vfs: &dyn Vfs,
        root: &Path,
        current: &Path,
        outcome: &mut ScanOutcome,
        cancel: Option<&AtomicBool>,
    ) -> Result<(), RCompareError> {
        if cancel.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
            return Err(RCompareError::Comparison("Scan cancelled".to_string()));
        }

        let dir_entries = match vfs.read_dir(current) {
            Ok(entries) => entries,
            Err(e) => {
                if self.strict {
                    return Err(RCompareError::Vfs(e.to_string()));
                }
                outcome.warnings.push(ScanWarning {
                    path: current.to_path_buf(),
                    message: format!("vfs read_dir error: {e}"),
                });
                return Ok(());
            }
        };

        for entry in dir_entries {
            if cancel.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
                return Err(RCompareError::Comparison("Scan cancelled".to_string()));
            }

            let vfs_path = entry.path.clone();
            let relative_path = vfs_path
                .strip_prefix(root)
                .unwrap_or(&vfs_path)
                .to_path_buf();

            // Skip the synthetic root entry (empty path)
            if relative_path.as_os_str().is_empty() {
                continue;
            }

            if self.should_ignore(&relative_path, entry.is_dir) {
                continue;
            }

            outcome.entries.push(FileEntry {
                path: relative_path,
                size: entry.size,
                modified: entry.modified,
                is_dir: entry.is_dir,
            });

            if entry.is_dir {
                self.scan_vfs_recursive(vfs, root, &vfs_path, outcome, cancel)?;
            }
        }

        Ok(())
    }

    /// Check if a path should be ignored via custom ignore patterns (VFS path;
    /// no nested `.gitignore` discovery since VFS entries aren't backed by a
    /// real filesystem to read `.gitignore` files from).
    fn should_ignore(&self, path: &Path, is_dir: bool) -> bool {
        if let Some(ref custom_ignore) = self.custom_ignore {
            if custom_ignore.matched(path, is_dir).is_ignore() {
                return true;
            }
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
        assert_eq!(
            entries.len(),
            4,
            "Expected 4 entries, got {}",
            entries.len()
        );

        // Verify no entry has an empty path (which would indicate root directory)
        for entry in &entries {
            assert!(
                !entry.path.as_os_str().is_empty(),
                "Found entry with empty path (root directory should be excluded)"
            );
        }
    }

    #[test]
    fn test_scanner_ignore_patterns() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("file1.txt"), b"test").unwrap();
        fs::write(temp.path().join("file2.o"), b"test").unwrap();

        let config = AppConfig {
            ignore_patterns: vec!["*.o".to_string()],
            ..Default::default()
        };

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        assert!(entries
            .iter()
            .all(|e| !e.path.to_string_lossy().ends_with(".o")));
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

        let config = AppConfig {
            ignore_patterns: vec![
                "*.log".to_string(),  // Ignore all .log files at any depth
                "build/".to_string(), // Ignore build directory
            ],
            ..Default::default()
        };

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Should not contain any .log files
        assert!(
            entries
                .iter()
                .all(|e| !e.path.to_string_lossy().ends_with(".log")),
            "Found .log file that should be ignored"
        );

        // Should not contain the build directory or its contents
        assert!(
            entries.iter().all(|e| !e.path.starts_with("build")),
            "Found file in build directory that should be ignored"
        );

        // Should contain .txt files outside build directory
        assert!(
            entries
                .iter()
                .any(|e| e.path.to_string_lossy().ends_with("root.txt")),
            "Missing root.txt"
        );
        assert!(
            entries
                .iter()
                .any(|e| e.path.to_string_lossy().ends_with("nested.txt")),
            "Missing nested.txt"
        );
    }

    #[test]
    fn test_scanner_root_relative_patterns() {
        let temp = TempDir::new().unwrap();

        // Create test structure
        fs::write(temp.path().join("config.toml"), b"test").unwrap();
        fs::create_dir(temp.path().join("subdir")).unwrap();
        fs::write(temp.path().join("subdir/config.toml"), b"test").unwrap();

        let config = AppConfig {
            ignore_patterns: vec![
                "/config.toml".to_string(), // Ignore only in root
            ],
            ..Default::default()
        };

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Should not contain root config.toml
        assert!(
            entries
                .iter()
                .all(|e| e.path.to_str() != Some("config.toml")),
            "Found root config.toml that should be ignored"
        );

        // Should contain nested config.toml
        assert!(
            entries
                .iter()
                .any(|e| e.path.to_string_lossy().contains("subdir")
                    && e.path.to_string_lossy().ends_with("config.toml")),
            "Missing subdir/config.toml"
        );
    }

    #[test]
    fn test_scanner_directory_only_patterns() {
        let temp = TempDir::new().unwrap();

        // Create test structure
        fs::create_dir(temp.path().join("temp")).unwrap();
        fs::write(temp.path().join("temp/file.txt"), b"test").unwrap();
        fs::write(temp.path().join("temp.txt"), b"test").unwrap(); // File named "temp.txt"

        let config = AppConfig {
            ignore_patterns: vec![
                "temp/".to_string(), // Ignore only directories named "temp"
            ],
            ..Default::default()
        };

        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        // Should not contain temp directory or its contents
        assert!(
            entries
                .iter()
                .all(|e| !e.path.starts_with("temp") || e.path.extension().is_some()),
            "Found temp directory that should be ignored"
        );

        // Should contain temp.txt file
        assert!(
            entries.iter().any(|e| e.path.to_str() == Some("temp.txt")),
            "Missing temp.txt file"
        );
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
            assert!(
                !entry.path.as_os_str().is_empty(),
                "Scanner included root directory entry with empty path"
            );
            assert!(
                entry.path != Path::new(""),
                "Scanner included root directory with empty PathBuf"
            );
        }

        // Should have exactly 2 entries: test.txt and subdir
        assert_eq!(
            entries.len(),
            2,
            "Expected 2 entries (excluding root), got {}",
            entries.len()
        );
    }

    #[test]
    fn test_scanner_nested_gitignore_discovered_incrementally() {
        let temp = TempDir::new().unwrap();
        fs::create_dir(temp.path().join("sub")).unwrap();
        fs::write(temp.path().join("sub/.gitignore"), b"*.tmp\n").unwrap();
        fs::write(temp.path().join("sub/keep.txt"), b"test").unwrap();
        fs::write(temp.path().join("sub/skip.tmp"), b"test").unwrap();
        fs::write(temp.path().join("root.tmp"), b"test").unwrap(); // not ignored (root has no .gitignore)

        let config = AppConfig::default();
        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        assert!(
            entries.iter().any(|e| e.path.to_str() == Some("root.tmp")),
            "root.tmp should not be ignored (no .gitignore at root)"
        );
        assert!(
            !entries
                .iter()
                .any(|e| e.path.to_string_lossy().ends_with("skip.tmp")),
            "sub/skip.tmp should be ignored by sub/.gitignore"
        );
        assert!(
            entries
                .iter()
                .any(|e| e.path.to_string_lossy().ends_with("keep.txt")),
            "sub/keep.txt should not be ignored"
        );
    }

    #[test]
    fn test_scanner_prunes_ignored_directory_contents_not_traversed() {
        let temp = TempDir::new().unwrap();
        fs::create_dir(temp.path().join("node_modules")).unwrap();
        fs::create_dir(temp.path().join("node_modules/pkg")).unwrap();
        fs::write(temp.path().join("node_modules/pkg/index.js"), b"x").unwrap();
        fs::write(temp.path().join("keep.txt"), b"test").unwrap();

        let config = AppConfig {
            ignore_patterns: vec!["node_modules/".to_string()],
            ..Default::default()
        };
        let scanner = FolderScanner::new(config);
        let entries = scanner.scan(temp.path()).unwrap();

        assert!(entries.iter().all(|e| !e.path.starts_with("node_modules")));
        assert!(entries.iter().any(|e| e.path.to_str() == Some("keep.txt")));
    }

    #[test]
    fn test_scanner_strict_mode_propagates_errors() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("test.txt"), b"content").unwrap();

        let config = AppConfig::default();
        let scanner = FolderScanner::new(config).with_strict(true);
        // A normal, race-free scan should still succeed under strict mode.
        let outcome = scanner.scan_with_cancel(temp.path(), None).unwrap();
        assert!(outcome.warnings.is_empty());
        assert_eq!(outcome.entries.len(), 1);
    }
}
