#[cfg(test)]
mod tests {
    use crate::vfs::LocalVfs;
    use rcompare_common::Vfs;
    use std::io::{Read, Write};
    use std::path::PathBuf;
    use tempfile::TempDir;

    // ============================================================================
    // LocalVfs Basic Tests
    // ============================================================================

    #[test]
    fn test_local_vfs_creation() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let instance_id = vfs.instance_id();
        assert!(instance_id.starts_with("local:"));
        assert!(instance_id.contains(temp_dir.path().to_str().unwrap()));
    }

    #[test]
    fn test_local_vfs_capabilities() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let caps = vfs.capabilities();
        assert!(caps.read, "LocalVfs should support reading");
        assert!(caps.write, "LocalVfs should support writing");
        assert!(caps.delete, "LocalVfs should support deletion");
        assert!(caps.rename, "LocalVfs should support renaming");
        assert!(
            caps.create_dir,
            "LocalVfs should support directory creation"
        );
        assert!(
            caps.set_mtime,
            "LocalVfs should support setting modification time"
        );
    }

    #[test]
    fn test_local_vfs_is_writable() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        assert!(vfs.is_writable(), "LocalVfs should be writable");
    }

    // ============================================================================
    // File Operations Tests
    // ============================================================================

    #[test]
    fn test_local_vfs_write_and_read_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("test.txt");
        let content = b"Hello, LocalVfs!";

        // Write file
        vfs.write_file(&path, content)
            .expect("Failed to write file");

        // Read file
        let mut reader = vfs.open_file(&path).expect("Failed to open file");
        let mut buffer = Vec::new();
        reader
            .read_to_end(&mut buffer)
            .expect("Failed to read file");

        assert_eq!(buffer, content);
    }

    #[test]
    fn test_local_vfs_create_file_with_writer() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("writer-test.txt");

        // Create and write using writer
        let mut writer = vfs.create_file(&path).expect("Failed to create file");
        writer.write_all(b"Line 1\n").expect("Failed to write");
        writer.write_all(b"Line 2\n").expect("Failed to write");
        writer.flush().expect("Failed to flush");
        drop(writer);

        // Read back
        let mut reader = vfs.open_file(&path).expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "Line 1\nLine 2\n");
    }

    #[test]
    fn test_local_vfs_metadata() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("metadata-test.txt");
        let content = b"1234567890";

        vfs.write_file(&path, content)
            .expect("Failed to write file");

        let meta = vfs.metadata(&path).expect("Failed to get metadata");
        assert_eq!(meta.size, 10);
        assert!(!meta.is_dir);
        assert!(!meta.is_symlink);
    }

    #[test]
    fn test_local_vfs_remove_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("remove-test.txt");

        vfs.write_file(&path, b"test")
            .expect("Failed to write file");
        assert!(vfs.metadata(&path).is_ok());

        vfs.remove_file(&path).expect("Failed to remove file");
        assert!(vfs.metadata(&path).is_err());
    }

    #[test]
    fn test_local_vfs_copy_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let src = PathBuf::from("source.txt");
        let dest = PathBuf::from("destination.txt");
        let content = b"Copy me!";

        vfs.write_file(&src, content)
            .expect("Failed to write source");
        vfs.copy_file(&src, &dest).expect("Failed to copy file");

        // Verify both files exist and have same content
        let mut reader = vfs.open_file(&dest).expect("Failed to open destination");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, content);
    }

    #[test]
    fn test_local_vfs_rename() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let old_path = PathBuf::from("old.txt");
        let new_path = PathBuf::from("new.txt");

        vfs.write_file(&old_path, b"content")
            .expect("Failed to write file");
        vfs.rename(&old_path, &new_path).expect("Failed to rename");

        assert!(vfs.metadata(&old_path).is_err());
        assert!(vfs.metadata(&new_path).is_ok());
    }

    // ============================================================================
    // Directory Operations Tests
    // ============================================================================

    #[test]
    fn test_local_vfs_create_dir() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let dir_path = PathBuf::from("test-dir");

        vfs.create_dir(&dir_path)
            .expect("Failed to create directory");

        let meta = vfs.metadata(&dir_path).expect("Failed to get metadata");
        assert!(meta.is_dir);
    }

    #[test]
    fn test_local_vfs_create_dir_all() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let nested_path = PathBuf::from("a/b/c/d");

        vfs.create_dir_all(&nested_path)
            .expect("Failed to create nested directories");

        let meta = vfs.metadata(&nested_path).expect("Failed to get metadata");
        assert!(meta.is_dir);
    }

    #[test]
    fn test_local_vfs_read_dir() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        // Create some test files
        vfs.write_file(&PathBuf::from("file1.txt"), b"content1")
            .expect("Failed to write");
        vfs.write_file(&PathBuf::from("file2.txt"), b"content2")
            .expect("Failed to write");
        vfs.create_dir(&PathBuf::from("subdir"))
            .expect("Failed to create dir");

        let entries = vfs
            .read_dir(&PathBuf::from(""))
            .expect("Failed to read directory");

        // Should have at least 3 entries
        assert!(
            entries.len() >= 3,
            "Expected at least 3 entries, got {}",
            entries.len()
        );

        let names: Vec<String> = entries
            .iter()
            .map(|e| e.path.file_name().unwrap().to_string_lossy().to_string())
            .collect();

        assert!(
            names.contains(&"file1.txt".to_string()),
            "Missing file1.txt"
        );
        assert!(
            names.contains(&"file2.txt".to_string()),
            "Missing file2.txt"
        );
        assert!(names.contains(&"subdir".to_string()), "Missing subdir");
    }

    #[test]
    fn test_local_vfs_read_dir_empty() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let entries = vfs
            .read_dir(&PathBuf::from(""))
            .expect("Failed to read empty directory");
        assert_eq!(entries.len(), 0);
    }

    #[test]
    fn test_local_vfs_read_dir_nested() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        vfs.create_dir(&PathBuf::from("subdir"))
            .expect("Failed to create dir");
        vfs.write_file(&PathBuf::from("subdir/file.txt"), b"nested")
            .expect("Failed to write");

        let entries = vfs
            .read_dir(&PathBuf::from("subdir"))
            .expect("Failed to read subdirectory");

        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].path.file_name().unwrap(), "file.txt");
    }

    // ============================================================================
    // Error Handling Tests
    // ============================================================================

    #[test]
    fn test_local_vfs_metadata_not_found() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let result = vfs.metadata(&PathBuf::from("nonexistent.txt"));
        assert!(result.is_err());
    }

    #[test]
    fn test_local_vfs_open_file_not_found() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let result = vfs.open_file(&PathBuf::from("missing.txt"));
        assert!(result.is_err());
    }

    #[test]
    fn test_local_vfs_open_file_on_directory() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        vfs.create_dir(&PathBuf::from("testdir"))
            .expect("Failed to create dir");

        let result = vfs.open_file(&PathBuf::from("testdir"));
        assert!(result.is_err());
    }

    #[test]
    fn test_local_vfs_read_dir_on_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        vfs.write_file(&PathBuf::from("file.txt"), b"content")
            .expect("Failed to write");

        let result = vfs.read_dir(&PathBuf::from("file.txt"));
        assert!(result.is_err());
    }

    #[test]
    fn test_local_vfs_remove_nonexistent_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let result = vfs.remove_file(&PathBuf::from("nonexistent.txt"));
        assert!(result.is_err());
    }

    // ============================================================================
    // Edge Case Tests
    // ============================================================================

    #[test]
    fn test_local_vfs_empty_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("empty.txt");

        vfs.write_file(&path, b"")
            .expect("Failed to write empty file");

        let meta = vfs.metadata(&path).expect("Failed to get metadata");
        assert_eq!(meta.size, 0);

        let mut reader = vfs.open_file(&path).expect("Failed to open empty file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read");
        assert_eq!(buffer.len(), 0);
    }

    #[test]
    fn test_local_vfs_large_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("large.bin");
        let size = 1024 * 1024; // 1MB
        let data = vec![42u8; size];

        vfs.write_file(&path, &data)
            .expect("Failed to write large file");

        let meta = vfs.metadata(&path).expect("Failed to get metadata");
        assert_eq!(meta.size, size as u64);

        let mut reader = vfs.open_file(&path).expect("Failed to open large file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read");
        assert_eq!(buffer.len(), size);
    }

    #[test]
    fn test_local_vfs_special_characters_in_filename() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        // Test various special characters
        let paths = vec![
            PathBuf::from("file with spaces.txt"),
            PathBuf::from("file-with-dashes.txt"),
            PathBuf::from("file_with_underscores.txt"),
            PathBuf::from("file.multiple.dots.txt"),
        ];

        for path in paths {
            vfs.write_file(&path, b"test")
                .unwrap_or_else(|_| panic!("Failed to write {:?}", path));
            assert!(
                vfs.metadata(&path).is_ok(),
                "Failed to get metadata for {:?}",
                path
            );
        }
    }

    #[test]
    fn test_local_vfs_deep_directory_structure() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        // Create a very deep directory structure
        let deep_path = PathBuf::from("a/b/c/d/e/f/g/h/i/j");
        vfs.create_dir_all(&deep_path)
            .expect("Failed to create deep directories");

        let file_path = deep_path.join("file.txt");
        vfs.write_file(&file_path, b"deep file")
            .expect("Failed to write file");

        assert!(vfs.metadata(&file_path).is_ok());
    }

    #[test]
    fn test_local_vfs_overwrite_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("overwrite.txt");

        // Write initial content
        vfs.write_file(&path, b"original")
            .expect("Failed to write file");

        // Overwrite with new content
        vfs.write_file(&path, b"modified")
            .expect("Failed to overwrite file");

        // Verify new content
        let mut reader = vfs.open_file(&path).expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "modified");
    }

    #[test]
    fn test_local_vfs_path_normalization() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        // Test paths with different separators
        vfs.write_file(&PathBuf::from("test.txt"), b"content")
            .expect("Failed to write");

        // Both should work
        assert!(vfs.metadata(&PathBuf::from("test.txt")).is_ok());
        assert!(vfs.metadata(&PathBuf::from("./test.txt")).is_ok());
    }

    // ============================================================================
    // Concurrent Access Tests
    // ============================================================================

    #[test]
    fn test_local_vfs_concurrent_reads() {
        use std::sync::Arc;
        use std::thread;

        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = Arc::new(LocalVfs::new(temp_dir.path().to_path_buf()));

        let path = PathBuf::from("concurrent.txt");
        vfs.write_file(&path, b"Concurrent test")
            .expect("Failed to write file");

        let mut handles = vec![];

        for _ in 0..10 {
            let vfs_clone = Arc::clone(&vfs);
            let path_clone = path.clone();

            let handle = thread::spawn(move || {
                let mut reader = vfs_clone.open_file(&path_clone).expect("Failed to open");
                let mut buffer = String::new();
                reader.read_to_string(&mut buffer).expect("Failed to read");
                assert_eq!(buffer, "Concurrent test");
            });

            handles.push(handle);
        }

        for handle in handles {
            handle.join().expect("Thread panicked");
        }
    }

    #[test]
    fn test_local_vfs_binary_data() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let path = PathBuf::from("binary.dat");

        // Write binary data with all byte values
        let binary_data: Vec<u8> = (0..=255).collect();
        vfs.write_file(&path, &binary_data)
            .expect("Failed to write binary");

        // Read back and verify
        let mut reader = vfs.open_file(&path).expect("Failed to open binary");
        let mut buffer = Vec::new();
        reader
            .read_to_end(&mut buffer)
            .expect("Failed to read binary");

        assert_eq!(buffer, binary_data);
    }

    #[test]
    fn test_local_vfs_symlink_access() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let vfs = LocalVfs::new(temp_dir.path().to_path_buf());

        let file_path = PathBuf::from("target.txt");
        vfs.write_file(&file_path, b"content")
            .expect("Failed to write file");

        #[cfg(unix)]
        {
            use std::os::unix::fs as unix_fs;

            let link_path = PathBuf::from("link.txt");
            let full_file_path = temp_dir.path().join(&file_path);
            let full_link_path = temp_dir.path().join(&link_path);

            unix_fs::symlink(&full_file_path, &full_link_path).expect("Failed to create symlink");

            // LocalVfs follows symlinks with fs::metadata, so we should be able to read through it
            let meta = vfs
                .metadata(&link_path)
                .expect("Failed to get metadata through symlink");
            assert!(!meta.is_dir);
            assert_eq!(meta.size, 7);

            // Should be able to read file content through symlink
            let mut reader = vfs
                .open_file(&link_path)
                .expect("Failed to open through symlink");
            let mut buffer = String::new();
            reader
                .read_to_string(&mut buffer)
                .expect("Failed to read through symlink");
            assert_eq!(buffer, "content");
        }
    }
}
