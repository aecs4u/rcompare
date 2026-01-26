//! Virtual VFS implementations for filtering, combining, and transforming VFS sources
//!
//! These VFS implementations wrap other VFS instances to provide additional functionality:
//! - `FilteredVfs`: Filter entries based on patterns or predicates
//! - `UnionVfs`: Combine multiple VFS sources into a single view

use rcompare_common::{FileEntry, FileMetadata, Vfs, VfsCapabilities, VfsError};
use std::io::Read;
use std::path::Path;
use std::sync::Arc;

/// A VFS wrapper that filters entries based on include/exclude patterns
///
/// FilteredVfs wraps another VFS and applies filtering rules to determine
/// which files and directories are visible. This is useful for:
/// - Applying .gitignore-style patterns
/// - Creating views of specific file types
/// - Excluding certain directories from comparison
pub struct FilteredVfs {
    instance_id: String,
    inner: Arc<dyn Vfs>,
    include_patterns: Vec<glob::Pattern>,
    exclude_patterns: Vec<glob::Pattern>,
}

impl FilteredVfs {
    /// Create a new FilteredVfs wrapping another VFS
    pub fn new(inner: Arc<dyn Vfs>) -> Self {
        let instance_id = format!("filtered:{}", inner.instance_id());
        Self {
            instance_id,
            inner,
            include_patterns: Vec::new(),
            exclude_patterns: Vec::new(),
        }
    }

    /// Add an include pattern (glob syntax)
    /// If any include patterns are set, only matching files are shown
    pub fn include(mut self, pattern: &str) -> Result<Self, VfsError> {
        let pat = glob::Pattern::new(pattern)
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidInput, e)))?;
        self.include_patterns.push(pat);
        Ok(self)
    }

    /// Add an exclude pattern (glob syntax)
    /// Matching files are hidden from view
    pub fn exclude(mut self, pattern: &str) -> Result<Self, VfsError> {
        let pat = glob::Pattern::new(pattern)
            .map_err(|e| VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidInput, e)))?;
        self.exclude_patterns.push(pat);
        Ok(self)
    }

    /// Add multiple include patterns
    pub fn include_many(mut self, patterns: &[&str]) -> Result<Self, VfsError> {
        for pattern in patterns {
            let pat = glob::Pattern::new(pattern).map_err(|e| {
                VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidInput, e))
            })?;
            self.include_patterns.push(pat);
        }
        Ok(self)
    }

    /// Add multiple exclude patterns
    pub fn exclude_many(mut self, patterns: &[&str]) -> Result<Self, VfsError> {
        for pattern in patterns {
            let pat = glob::Pattern::new(pattern).map_err(|e| {
                VfsError::Io(std::io::Error::new(std::io::ErrorKind::InvalidInput, e))
            })?;
            self.exclude_patterns.push(pat);
        }
        Ok(self)
    }

    /// Check if a path should be visible based on include/exclude patterns
    fn is_visible(&self, path: &Path) -> bool {
        let path_str = path.to_string_lossy();

        // Check exclude patterns first
        for pattern in &self.exclude_patterns {
            if pattern.matches(&path_str) {
                return false;
            }
        }

        // If no include patterns, everything is included
        if self.include_patterns.is_empty() {
            return true;
        }

        // Check include patterns
        for pattern in &self.include_patterns {
            if pattern.matches(&path_str) {
                return true;
            }
        }

        false
    }
}

impl Vfs for FilteredVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        if !self.is_visible(path) {
            return Err(VfsError::NotFound(path.display().to_string()));
        }
        self.inner.metadata(path)
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let entries = self.inner.read_dir(path)?;
        Ok(entries
            .into_iter()
            .filter(|e| self.is_visible(&e.path))
            .collect())
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        if !self.is_visible(path) {
            return Err(VfsError::NotFound(path.display().to_string()));
        }
        self.inner.open_file(path)
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        if !self.is_visible(path) {
            return Err(VfsError::NotFound(path.display().to_string()));
        }
        self.inner.remove_file(path)
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        if !self.is_visible(src) {
            return Err(VfsError::NotFound(src.display().to_string()));
        }
        self.inner.copy_file(src, dest)
    }

    fn is_writable(&self) -> bool {
        self.inner.is_writable()
    }

    fn capabilities(&self) -> VfsCapabilities {
        self.inner.capabilities()
    }
}

/// A VFS that combines multiple VFS sources into a single unified view
///
/// UnionVfs presents files from multiple VFS sources as if they were
/// a single filesystem. Later sources take precedence for conflicts.
/// This is useful for:
/// - Combining local files with archive contents
/// - Layering multiple directories
/// - Creating overlay filesystems
pub struct UnionVfs {
    instance_id: String,
    layers: Vec<Arc<dyn Vfs>>,
}

impl UnionVfs {
    /// Create a new empty UnionVfs
    pub fn new() -> Self {
        Self {
            instance_id: "union:".to_string(),
            layers: Vec::new(),
        }
    }

    /// Add a VFS layer (later layers take precedence)
    pub fn add_layer(mut self, vfs: Arc<dyn Vfs>) -> Self {
        self.instance_id = format!("{}+{}", self.instance_id, vfs.instance_id());
        self.layers.push(vfs);
        self
    }

    /// Find the layer that contains a given path
    fn find_layer(&self, path: &Path) -> Option<&Arc<dyn Vfs>> {
        // Search from last (highest priority) to first
        self.layers.iter().rev().find(|&layer| layer.exists(path)).map(|v| v as _)
    }
}

impl Default for UnionVfs {
    fn default() -> Self {
        Self::new()
    }
}

impl Vfs for UnionVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        self.find_layer(path)
            .ok_or_else(|| VfsError::NotFound(path.display().to_string()))?
            .metadata(path)
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let mut all_entries: std::collections::HashMap<std::path::PathBuf, FileEntry> =
            std::collections::HashMap::new();

        // Collect entries from all layers, later layers override earlier ones
        for layer in &self.layers {
            if let Ok(entries) = layer.read_dir(path) {
                for entry in entries {
                    all_entries.insert(entry.path.clone(), entry);
                }
            }
        }

        if all_entries.is_empty() {
            // Check if any layer has this as a directory
            let is_dir = self
                .layers
                .iter()
                .any(|l| l.metadata(path).map(|m| m.is_dir).unwrap_or(false));

            if !is_dir {
                return Err(VfsError::NotADirectory(path.display().to_string()));
            }
        }

        Ok(all_entries.into_values().collect())
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        self.find_layer(path)
            .ok_or_else(|| VfsError::NotFound(path.display().to_string()))?
            .open_file(path)
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        // Find writable layer containing this file
        for layer in self.layers.iter().rev() {
            if layer.exists(path) && layer.is_writable() {
                return layer.remove_file(path);
            }
        }
        Err(VfsError::Unsupported(
            "No writable layer contains this file".to_string(),
        ))
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        // Find source layer and writable destination layer
        let src_layer = self
            .find_layer(src)
            .ok_or_else(|| VfsError::NotFound(src.display().to_string()))?;

        // Find first writable layer for destination
        for layer in self.layers.iter().rev() {
            if layer.is_writable() {
                // Read from source, write to destination layer
                let mut reader = src_layer.open_file(src)?;
                let mut content = Vec::new();
                reader.read_to_end(&mut content)?;

                let mut writer = layer.create_file(dest)?;
                std::io::Write::write_all(&mut writer, &content)?;
                return Ok(());
            }
        }

        Err(VfsError::Unsupported(
            "No writable layer available".to_string(),
        ))
    }

    fn is_writable(&self) -> bool {
        self.layers.iter().any(|l| l.is_writable())
    }

    fn capabilities(&self) -> VfsCapabilities {
        // Combine capabilities from all layers
        let mut caps = VfsCapabilities::default();
        for layer in &self.layers {
            let layer_caps = layer.capabilities();
            caps.read = caps.read || layer_caps.read;
            caps.write = caps.write || layer_caps.write;
            caps.delete = caps.delete || layer_caps.delete;
            caps.rename = caps.rename || layer_caps.rename;
            caps.create_dir = caps.create_dir || layer_caps.create_dir;
            caps.set_mtime = caps.set_mtime || layer_caps.set_mtime;
        }
        caps
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vfs::LocalVfs;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_filtered_vfs_exclude() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("file.txt"), b"content").unwrap();
        fs::write(temp.path().join("file.log"), b"log").unwrap();
        fs::create_dir(temp.path().join("dir")).unwrap();
        fs::write(temp.path().join("dir/nested.txt"), b"nested").unwrap();

        let local = Arc::new(LocalVfs::new(temp.path().to_path_buf()));
        let filtered = FilteredVfs::new(local).exclude("*.log").unwrap();

        let entries = filtered.read_dir(Path::new("")).unwrap();
        let names: Vec<_> = entries
            .iter()
            .map(|e| e.path.to_string_lossy().to_string())
            .collect();

        assert!(names.contains(&"file.txt".to_string()));
        assert!(!names.contains(&"file.log".to_string()));
        assert!(names.contains(&"dir".to_string()));
    }

    #[test]
    fn test_filtered_vfs_include() {
        let temp = TempDir::new().unwrap();
        fs::write(temp.path().join("file.txt"), b"content").unwrap();
        fs::write(temp.path().join("file.rs"), b"code").unwrap();
        fs::write(temp.path().join("file.log"), b"log").unwrap();

        let local = Arc::new(LocalVfs::new(temp.path().to_path_buf()));
        let filtered = FilteredVfs::new(local)
            .include("*.txt")
            .unwrap()
            .include("*.rs")
            .unwrap();

        let entries = filtered.read_dir(Path::new("")).unwrap();
        let names: Vec<_> = entries
            .iter()
            .map(|e| e.path.to_string_lossy().to_string())
            .collect();

        assert!(names.contains(&"file.txt".to_string()));
        assert!(names.contains(&"file.rs".to_string()));
        assert!(!names.contains(&"file.log".to_string()));
    }

    #[test]
    fn test_union_vfs_basic() {
        let temp1 = TempDir::new().unwrap();
        let temp2 = TempDir::new().unwrap();

        fs::write(temp1.path().join("file1.txt"), b"from layer 1").unwrap();
        fs::write(temp2.path().join("file2.txt"), b"from layer 2").unwrap();

        let layer1 = Arc::new(LocalVfs::new(temp1.path().to_path_buf()));
        let layer2 = Arc::new(LocalVfs::new(temp2.path().to_path_buf()));

        let union = UnionVfs::new().add_layer(layer1).add_layer(layer2);

        // Should see files from both layers
        assert!(union.exists(Path::new("file1.txt")));
        assert!(union.exists(Path::new("file2.txt")));
    }

    #[test]
    fn test_union_vfs_override() {
        let temp1 = TempDir::new().unwrap();
        let temp2 = TempDir::new().unwrap();

        fs::write(temp1.path().join("shared.txt"), b"from layer 1").unwrap();
        fs::write(temp2.path().join("shared.txt"), b"from layer 2").unwrap();

        let layer1 = Arc::new(LocalVfs::new(temp1.path().to_path_buf()));
        let layer2 = Arc::new(LocalVfs::new(temp2.path().to_path_buf()));

        let union = UnionVfs::new().add_layer(layer1).add_layer(layer2);

        // Layer 2 should take precedence
        let mut reader = union.open_file(Path::new("shared.txt")).unwrap();
        let mut content = String::new();
        reader.read_to_string(&mut content).unwrap();
        assert_eq!(content, "from layer 2");
    }
}
