#[cfg(test)]
mod tests {
    use crate::vfs::{FilteredVfs, UnionVfs, LocalVfs};
    use rcompare_common::Vfs;
    use std::io::{Read, Write};
    use std::path::PathBuf;
    use std::sync::Arc;
    use tempfile::TempDir;

    // ============================================================================
    // FilteredVfs Tests
    // ============================================================================

    #[test]
    fn test_filtered_vfs_creation() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        let filtered = FilteredVfs::new(local_vfs);
        let instance_id = filtered.instance_id();

        assert!(instance_id.starts_with("filtered:"));
    }

    #[test]
    fn test_filtered_vfs_include_pattern() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        // Create test files
        local_vfs.write_file(&PathBuf::from("file1.txt"), b"content1").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file2.rs"), b"content2").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file3.txt"), b"content3").expect("Failed to write");

        // Filter to only show .txt files
        let filtered = FilteredVfs::new(local_vfs)
            .include("*.txt")
            .expect("Failed to add include pattern");

        let entries = filtered.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        // Should only see .txt files
        assert_eq!(entries.len(), 2);
        for entry in &entries {
            assert!(entry.path.to_string_lossy().ends_with(".txt"));
        }
    }

    #[test]
    fn test_filtered_vfs_exclude_pattern() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        // Create test files
        local_vfs.write_file(&PathBuf::from("file1.txt"), b"content1").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file2.log"), b"content2").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file3.txt"), b"content3").expect("Failed to write");

        // Exclude .log files
        let filtered = FilteredVfs::new(local_vfs)
            .exclude("*.log")
            .expect("Failed to add exclude pattern");

        let entries = filtered.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        // Should not see .log files
        for entry in &entries {
            assert!(!entry.path.to_string_lossy().ends_with(".log"));
        }
    }

    #[test]
    fn test_filtered_vfs_multiple_includes() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        // Create test files
        local_vfs.write_file(&PathBuf::from("file.txt"), b"content").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file.rs"), b"content").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file.md"), b"content").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file.log"), b"content").expect("Failed to write");

        // Include only .txt and .rs files
        let filtered = FilteredVfs::new(local_vfs)
            .include_many(&["*.txt", "*.rs"])
            .expect("Failed to add include patterns");

        let entries = filtered.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        assert_eq!(entries.len(), 2);
        for entry in &entries {
            let path_str = entry.path.to_string_lossy();
            assert!(path_str.ends_with(".txt") || path_str.ends_with(".rs"));
        }
    }

    #[test]
    fn test_filtered_vfs_multiple_excludes() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        // Create test files
        local_vfs.write_file(&PathBuf::from("file.txt"), b"content").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file.tmp"), b"content").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("file.log"), b"content").expect("Failed to write");

        // Exclude .tmp and .log files
        let filtered = FilteredVfs::new(local_vfs)
            .exclude_many(&["*.tmp", "*.log"])
            .expect("Failed to add exclude patterns");

        let entries = filtered.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].path.file_name().unwrap(), "file.txt");
    }

    #[test]
    fn test_filtered_vfs_include_and_exclude() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        // Create test files
        local_vfs.write_file(&PathBuf::from("important.txt"), b"content").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("temp.txt"), b"content").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("data.log"), b"content").expect("Failed to write");

        // Include .txt but exclude temp.*
        let filtered = FilteredVfs::new(local_vfs)
            .include("*.txt")
            .expect("Failed to add include")
            .exclude("temp.*")
            .expect("Failed to add exclude");

        let entries = filtered.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].path.file_name().unwrap(), "important.txt");
    }

    #[test]
    fn test_filtered_vfs_open_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        local_vfs.write_file(&PathBuf::from("data.txt"), b"File content").expect("Failed to write");

        let filtered = FilteredVfs::new(local_vfs)
            .include("*.txt")
            .expect("Failed to add pattern");

        // Should be able to read the file
        let mut reader = filtered.open_file(&PathBuf::from("data.txt")).expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "File content");
    }

    #[test]
    fn test_filtered_vfs_metadata() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        local_vfs.write_file(&PathBuf::from("test.txt"), b"12345").expect("Failed to write");

        let filtered = FilteredVfs::new(local_vfs);

        let meta = filtered.metadata(&PathBuf::from("test.txt")).expect("Failed to get metadata");
        assert_eq!(meta.size, 5);
        assert!(!meta.is_dir);
    }

    #[test]
    fn test_filtered_vfs_capabilities() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        let filtered = FilteredVfs::new(local_vfs);
        let caps = filtered.capabilities();

        // Should inherit capabilities from underlying VFS
        assert!(caps.read);
        assert!(caps.write);
    }

    #[test]
    fn test_filtered_vfs_invalid_pattern() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        // Try to add an invalid glob pattern
        let result = FilteredVfs::new(local_vfs).include("[invalid");

        assert!(result.is_err(), "Should fail with invalid pattern");
    }

    // ============================================================================
    // UnionVfs Tests
    // ============================================================================

    #[test]
    fn test_union_vfs_creation() {
        let union = UnionVfs::new();
        let instance_id = union.instance_id();

        assert!(instance_id.starts_with("union:"));
    }

    #[test]
    fn test_union_vfs_single_layer() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        local_vfs.write_file(&PathBuf::from("file.txt"), b"content").expect("Failed to write");

        let union = UnionVfs::new().add_layer(local_vfs);

        // Should be able to read from the single layer
        let entries = union.read_dir(&PathBuf::from("")).expect("Failed to read dir");
        assert_eq!(entries.len(), 1);
    }

    #[test]
    fn test_union_vfs_multiple_layers() {
        let temp_dir1 = TempDir::new().expect("Failed to create temp dir 1");
        let temp_dir2 = TempDir::new().expect("Failed to create temp dir 2");

        let vfs1 = Arc::new(LocalVfs::new(temp_dir1.path().to_path_buf()));
        let vfs2 = Arc::new(LocalVfs::new(temp_dir2.path().to_path_buf()));

        // Create files in each layer
        vfs1.write_file(&PathBuf::from("file1.txt"), b"layer1").expect("Failed to write");
        vfs2.write_file(&PathBuf::from("file2.txt"), b"layer2").expect("Failed to write");

        let union = UnionVfs::new()
            .add_layer(vfs1)
            .add_layer(vfs2);

        // Should see files from both layers
        let entries = union.read_dir(&PathBuf::from("")).expect("Failed to read dir");
        assert!(entries.len() >= 2);
    }

    #[test]
    fn test_union_vfs_layer_priority() {
        let temp_dir1 = TempDir::new().expect("Failed to create temp dir 1");
        let temp_dir2 = TempDir::new().expect("Failed to create temp dir 2");

        let vfs1 = Arc::new(LocalVfs::new(temp_dir1.path().to_path_buf()));
        let vfs2 = Arc::new(LocalVfs::new(temp_dir2.path().to_path_buf()));

        // Create same file in both layers with different content
        vfs1.write_file(&PathBuf::from("data.txt"), b"from layer1").expect("Failed to write");
        vfs2.write_file(&PathBuf::from("data.txt"), b"from layer2").expect("Failed to write");

        // Later layers take precedence
        let union = UnionVfs::new()
            .add_layer(vfs1)
            .add_layer(vfs2);

        // Should read from layer2 (last added)
        let mut reader = union.open_file(&PathBuf::from("data.txt")).expect("Failed to open");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "from layer2");
    }

    #[test]
    fn test_union_vfs_metadata() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        local_vfs.write_file(&PathBuf::from("test.txt"), b"12345").expect("Failed to write");

        let union = UnionVfs::new().add_layer(local_vfs);

        let meta = union.metadata(&PathBuf::from("test.txt")).expect("Failed to get metadata");
        assert_eq!(meta.size, 5);
    }

    #[test]
    fn test_union_vfs_file_not_found() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        let union = UnionVfs::new().add_layer(local_vfs);

        let result = union.open_file(&PathBuf::from("nonexistent.txt"));
        assert!(result.is_err(), "Should fail for nonexistent file");
    }

    #[test]
    fn test_union_vfs_capabilities() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        let union = UnionVfs::new().add_layer(local_vfs);
        let caps = union.capabilities();

        // Union should have limited capabilities (read-only nature)
        assert!(caps.read);
    }

    #[test]
    fn test_union_vfs_empty() {
        let union = UnionVfs::new();

        // Reading from empty union should fail (no layers to check)
        let result = union.read_dir(&PathBuf::from(""));
        assert!(result.is_err(), "Empty union should fail to read dir");
    }

    // ============================================================================
    // Integration Tests - Combining Filters and Unions
    // ============================================================================

    #[test]
    fn test_filtered_union_vfs() {
        let temp_dir1 = TempDir::new().expect("Failed to create temp dir 1");
        let temp_dir2 = TempDir::new().expect("Failed to create temp dir 2");

        let vfs1 = Arc::new(LocalVfs::new(temp_dir1.path().to_path_buf()));
        let vfs2 = Arc::new(LocalVfs::new(temp_dir2.path().to_path_buf()));

        // Create various files
        vfs1.write_file(&PathBuf::from("code.rs"), b"rust code").expect("Failed to write");
        vfs1.write_file(&PathBuf::from("data.txt"), b"text data").expect("Failed to write");
        vfs2.write_file(&PathBuf::from("lib.rs"), b"library").expect("Failed to write");
        vfs2.write_file(&PathBuf::from("readme.md"), b"docs").expect("Failed to write");

        // Create union
        let union = Arc::new(UnionVfs::new()
            .add_layer(vfs1)
            .add_layer(vfs2));

        // Apply filter to only show .rs files
        let filtered = FilteredVfs::new(union)
            .include("*.rs")
            .expect("Failed to add pattern");

        let entries = filtered.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        // Should only see .rs files from both layers
        assert!(entries.len() >= 2);
        for entry in &entries {
            assert!(entry.path.to_string_lossy().ends_with(".rs"));
        }
    }

    #[test]
    fn test_union_of_filtered_vfs() {
        let temp_dir1 = TempDir::new().expect("Failed to create temp dir 1");
        let temp_dir2 = TempDir::new().expect("Failed to create temp dir 2");

        let vfs1 = Arc::new(LocalVfs::new(temp_dir1.path().to_path_buf()));
        let vfs2 = Arc::new(LocalVfs::new(temp_dir2.path().to_path_buf()));

        // Create files
        vfs1.write_file(&PathBuf::from("source.rs"), b"code").expect("Failed to write");
        vfs1.write_file(&PathBuf::from("temp.log"), b"log").expect("Failed to write");
        vfs2.write_file(&PathBuf::from("lib.rs"), b"library").expect("Failed to write");
        vfs2.write_file(&PathBuf::from("debug.log"), b"debug").expect("Failed to write");

        // Filter each VFS separately
        let filtered1 = Arc::new(FilteredVfs::new(vfs1)
            .exclude("*.log")
            .expect("Failed to exclude"));

        let filtered2 = Arc::new(FilteredVfs::new(vfs2)
            .exclude("*.log")
            .expect("Failed to exclude"));

        // Combine filtered VFS instances
        let union = UnionVfs::new()
            .add_layer(filtered1)
            .add_layer(filtered2);

        let entries = union.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        // Should only see .rs files (logs filtered out)
        for entry in &entries {
            assert!(!entry.path.to_string_lossy().ends_with(".log"));
        }
    }

    #[test]
    fn test_nested_filtering() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let local_vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        // Create test files
        local_vfs.write_file(&PathBuf::from("important.txt"), b"keep").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("temp.txt"), b"temp").expect("Failed to write");
        local_vfs.write_file(&PathBuf::from("data.log"), b"log").expect("Failed to write");

        // First filter: include only .txt files
        let filtered1 = Arc::new(FilteredVfs::new(local_vfs)
            .include("*.txt")
            .expect("Failed to include"));

        // Second filter: exclude temp files
        let filtered2 = FilteredVfs::new(filtered1)
            .exclude("temp.*")
            .expect("Failed to exclude");

        let entries = filtered2.read_dir(&PathBuf::from("")).expect("Failed to read dir");

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].path.file_name().unwrap(), "important.txt");
    }

}
