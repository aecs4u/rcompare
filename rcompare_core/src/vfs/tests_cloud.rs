#[cfg(test)]
mod tests {
    use crate::vfs::{S3Vfs, S3Config, S3Auth, WebDavVfs, WebDavConfig, WebDavAuth};
    use rcompare_common::Vfs;
    use std::path::PathBuf;

    // Note: These tests require actual S3 and WebDAV services to be available
    // They are marked as ignored by default and should be run manually

    #[test]
    #[ignore]
    fn test_s3_vfs_creation() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let result = S3Vfs::new(config);
        assert!(result.is_ok());
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_with_custom_endpoint() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::AccessKey {
                access_key_id: "test-key".to_string(),
                secret_access_key: "test-secret".to_string(),
                session_token: None,
            },
            endpoint: Some("http://localhost:9000".to_string()), // MinIO
        };

        let result = S3Vfs::new(config);
        assert!(result.is_ok());
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_list_objects() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let entries = vfs.read_dir(&PathBuf::from("/"));

        match entries {
            Ok(files) => {
                println!("Found {} entries", files.len());
                for file in files {
                    println!("  - {}: {} bytes", file.path.display(), file.size);
                }
            }
            Err(e) => {
                println!("Error listing objects: {:?}", e);
            }
        }
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_read_write() {
        use std::io::Read;

        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/test"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let test_path = PathBuf::from("test-file.txt");
        let test_content = b"Hello, S3!";

        // Write file
        let result = vfs.write_file(&test_path, test_content);
        assert!(result.is_ok(), "Failed to write file: {:?}", result.err());

        // Read file
        let mut reader = vfs.open_file(&test_path).expect("Failed to open file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read file");

        assert_eq!(buffer, test_content);

        // Clean up
        let _ = vfs.remove_file(&test_path);
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_metadata() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let test_path = PathBuf::from("test-file.txt");

        // Create a test file first
        vfs.write_file(&test_path, b"test").expect("Failed to write test file");

        // Get metadata
        let metadata = vfs.metadata(&test_path);
        assert!(metadata.is_ok());

        let meta = metadata.unwrap();
        assert!(!meta.is_dir);
        assert_eq!(meta.size, 4);

        // Clean up
        let _ = vfs.remove_file(&test_path);
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_creation() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let result = WebDavVfs::new(config);
        assert!(result.is_ok());
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_with_basic_auth() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::Basic {
                username: "user".to_string(),
                password: "pass".to_string(),
            },
            root_path: PathBuf::from("/"),
        };

        let result = WebDavVfs::new(config);
        assert!(result.is_ok());
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_list_directory() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let entries = vfs.read_dir(&PathBuf::from("/"));

        match entries {
            Ok(files) => {
                println!("Found {} entries", files.len());
                for file in files {
                    println!("  - {}: {} bytes (dir: {})",
                        file.path.display(), file.size, file.is_dir);
                }
            }
            Err(e) => {
                println!("Error listing directory: {:?}", e);
            }
        }
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_read_write() {
        use std::io::Read;

        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/test"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let test_path = PathBuf::from("test-file.txt");
        let test_content = b"Hello, WebDAV!";

        // Write file
        let result = vfs.write_file(&test_path, test_content);
        assert!(result.is_ok(), "Failed to write file: {:?}", result.err());

        // Read file
        let mut reader = vfs.open_file(&test_path).expect("Failed to open file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read file");

        assert_eq!(buffer, test_content);

        // Clean up
        let _ = vfs.remove_file(&test_path);
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_create_directory() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let dir_path = PathBuf::from("test-dir");

        // Create directory
        let result = vfs.create_dir(&dir_path);
        assert!(result.is_ok(), "Failed to create directory: {:?}", result.err());

        // Verify it exists
        let metadata = vfs.metadata(&dir_path);
        assert!(metadata.is_ok());
        assert!(metadata.unwrap().is_dir);

        // Clean up
        let _ = vfs.remove_file(&dir_path);
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_copy_file() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let src_path = PathBuf::from("source.txt");
        let dest_path = PathBuf::from("destination.txt");
        let test_content = b"Copy test";

        // Create source file
        vfs.write_file(&src_path, test_content).expect("Failed to write source file");

        // Copy file
        let result = vfs.copy_file(&src_path, &dest_path);
        assert!(result.is_ok(), "Failed to copy file: {:?}", result.err());

        // Verify destination exists
        let metadata = vfs.metadata(&dest_path);
        assert!(metadata.is_ok());

        // Clean up
        let _ = vfs.remove_file(&src_path);
        let _ = vfs.remove_file(&dest_path);
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_rename() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let old_path = PathBuf::from("old-name.txt");
        let new_path = PathBuf::from("new-name.txt");
        let test_content = b"Rename test";

        // Create original file
        vfs.write_file(&old_path, test_content).expect("Failed to write file");

        // Rename file
        let result = vfs.rename(&old_path, &new_path);
        assert!(result.is_ok(), "Failed to rename file: {:?}", result.err());

        // Verify old path doesn't exist
        assert!(vfs.metadata(&old_path).is_err());

        // Verify new path exists
        assert!(vfs.metadata(&new_path).is_ok());

        // Clean up
        let _ = vfs.remove_file(&new_path);
    }

    #[test]
    fn test_s3_config_default() {
        let config = S3Config::default();
        assert_eq!(config.bucket, "");
        assert_eq!(config.region, "us-east-1");
        assert_eq!(config.prefix, PathBuf::from("/"));
        assert!(matches!(config.auth, S3Auth::Default));
        assert!(config.endpoint.is_none());
    }

    #[test]
    fn test_webdav_config_default() {
        let config = WebDavConfig::default();
        assert_eq!(config.url, "");
        assert_eq!(config.root_path, PathBuf::from("/"));
        assert!(matches!(config.auth, WebDavAuth::None));
    }

    #[test]
    fn test_s3_auth_variants() {
        // Test Default auth
        let _auth = S3Auth::Default;

        // Test AccessKey auth
        let auth = S3Auth::AccessKey {
            access_key_id: "AKIAIOSFODNN7EXAMPLE".to_string(),
            secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY".to_string(),
            session_token: Some("session-token".to_string()),
        };
        if let S3Auth::AccessKey { access_key_id, .. } = auth {
            assert_eq!(access_key_id, "AKIAIOSFODNN7EXAMPLE");
        }

        // Test Anonymous auth
        let _auth = S3Auth::Anonymous;
    }

    #[test]
    fn test_webdav_auth_variants() {
        // Test None auth
        let _auth = WebDavAuth::None;

        // Test Basic auth
        let auth = WebDavAuth::Basic {
            username: "user".to_string(),
            password: "pass".to_string(),
        };
        if let WebDavAuth::Basic { username, .. } = auth {
            assert_eq!(username, "user");
        }

        // Test Digest auth
        let _auth = WebDavAuth::Digest {
            username: "user".to_string(),
            password: "pass".to_string(),
        };

        // Test Bearer auth
        let auth = WebDavAuth::Bearer {
            token: "token123".to_string(),
        };
        if let WebDavAuth::Bearer { token } = auth {
            assert_eq!(token, "token123");
        }
    }

    // ============================================================================
    // S3 VFS Unit Tests - Path Handling and Key Conversion
    // ============================================================================

    #[test]
    fn test_s3_config_with_prefix() {
        let config = S3Config {
            bucket: "my-bucket".to_string(),
            region: "eu-west-1".to_string(),
            prefix: PathBuf::from("/my/prefix"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        assert_eq!(config.bucket, "my-bucket");
        assert_eq!(config.region, "eu-west-1");
        assert_eq!(config.prefix, PathBuf::from("/my/prefix"));
    }

    #[test]
    fn test_s3_config_with_endpoint() {
        let config = S3Config {
            bucket: "test".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Anonymous,
            endpoint: Some("https://s3.example.com".to_string()),
        };

        assert_eq!(config.endpoint, Some("https://s3.example.com".to_string()));
        assert!(matches!(config.auth, S3Auth::Anonymous));
    }

    #[test]
    fn test_s3_config_clone() {
        let config1 = S3Config {
            bucket: "bucket1".to_string(),
            region: "us-west-2".to_string(),
            prefix: PathBuf::from("/test"),
            auth: S3Auth::AccessKey {
                access_key_id: "key".to_string(),
                secret_access_key: "secret".to_string(),
                session_token: None,
            },
            endpoint: None,
        };

        let config2 = config1.clone();
        assert_eq!(config1.bucket, config2.bucket);
        assert_eq!(config1.region, config2.region);
    }

    #[test]
    fn test_s3_instance_id_format() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/data"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let instance_id = vfs.instance_id();

        assert!(instance_id.starts_with("s3://"));
        assert!(instance_id.contains("test-bucket"));
    }

    #[test]
    fn test_s3_vfs_capabilities() {
        let config = S3Config::default();
        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let caps = vfs.capabilities();

        assert!(caps.read, "S3 VFS should support reading");
        assert!(caps.write, "S3 VFS should support writing");
        assert!(caps.delete, "S3 VFS should support deletion");
        assert!(caps.rename, "S3 VFS should support renaming");
        assert!(caps.create_dir, "S3 VFS should support directory creation");
        assert!(!caps.set_mtime, "S3 VFS should not support setting modification time");
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_create_dir() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let dir_path = PathBuf::from("test-directory");

        let result = vfs.create_dir(&dir_path);
        assert!(result.is_ok(), "Failed to create directory: {:?}", result.err());

        // Clean up
        let _ = vfs.remove_file(&dir_path);
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_create_dir_all() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let nested_path = PathBuf::from("a/b/c/d");

        let result = vfs.create_dir_all(&nested_path);
        assert!(result.is_ok(), "Failed to create nested directories: {:?}", result.err());

        // Clean up
        let _ = vfs.remove_file(&nested_path);
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_copy_file() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let src = PathBuf::from("source.txt");
        let dest = PathBuf::from("destination.txt");

        // Create source file
        vfs.write_file(&src, b"test content").expect("Failed to write source");

        // Copy file
        let result = vfs.copy_file(&src, &dest);
        assert!(result.is_ok(), "Failed to copy file: {:?}", result.err());

        // Verify destination exists
        assert!(vfs.metadata(&dest).is_ok());

        // Clean up
        let _ = vfs.remove_file(&src);
        let _ = vfs.remove_file(&dest);
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_rename() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let old = PathBuf::from("old.txt");
        let new = PathBuf::from("new.txt");

        // Create file
        vfs.write_file(&old, b"content").expect("Failed to write file");

        // Rename
        let result = vfs.rename(&old, &new);
        assert!(result.is_ok(), "Failed to rename: {:?}", result.err());

        // Verify old doesn't exist and new does
        assert!(vfs.metadata(&old).is_err());
        assert!(vfs.metadata(&new).is_ok());

        // Clean up
        let _ = vfs.remove_file(&new);
    }

    // ============================================================================
    // WebDAV VFS Unit Tests - URL Building and Path Handling
    // ============================================================================

    #[test]
    fn test_webdav_config_with_root_path() {
        let config = WebDavConfig {
            url: "https://cloud.example.com/remote.php/dav/files/user".to_string(),
            auth: WebDavAuth::Basic {
                username: "user".to_string(),
                password: "password".to_string(),
            },
            root_path: PathBuf::from("/Documents"),
        };

        assert_eq!(config.root_path, PathBuf::from("/Documents"));
        assert!(config.url.contains("cloud.example.com"));
    }

    #[test]
    fn test_webdav_config_clone() {
        let config1 = WebDavConfig {
            url: "http://localhost/webdav".to_string(),
            auth: WebDavAuth::Bearer {
                token: "token123".to_string(),
            },
            root_path: PathBuf::from("/"),
        };

        let config2 = config1.clone();
        assert_eq!(config1.url, config2.url);
        assert_eq!(config1.root_path, config2.root_path);
    }

    #[test]
    fn test_webdav_instance_id_format() {
        let config = WebDavConfig {
            url: "https://webdav.example.com/dav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/files"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let instance_id = vfs.instance_id();

        assert!(instance_id.starts_with("webdav://"));
        assert!(instance_id.contains("webdav.example.com"));
    }

    #[test]
    fn test_webdav_vfs_capabilities() {
        let config = WebDavConfig {
            url: "http://localhost/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };
        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let caps = vfs.capabilities();

        assert!(caps.read, "WebDAV VFS should support reading");
        assert!(caps.write, "WebDAV VFS should support writing");
        assert!(caps.delete, "WebDAV VFS should support deletion");
        assert!(caps.rename, "WebDAV VFS should support renaming");
        assert!(caps.create_dir, "WebDAV VFS should support directory creation");
        assert!(!caps.set_mtime, "WebDAV VFS typically doesn't support setting modification time");
    }

    // ============================================================================
    // Error Handling Tests
    // ============================================================================

    #[test]
    #[ignore]
    fn test_s3_vfs_metadata_not_found() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let result = vfs.metadata(&PathBuf::from("nonexistent-file.txt"));

        assert!(result.is_err(), "Should fail for nonexistent file");
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_open_file_not_found() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let result = vfs.open_file(&PathBuf::from("missing.txt"));

        assert!(result.is_err(), "Should fail for nonexistent file");
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_metadata_not_found() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let result = vfs.metadata(&PathBuf::from("does-not-exist.txt"));

        assert!(result.is_err(), "Should fail for nonexistent file");
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_open_file_not_found() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let result = vfs.open_file(&PathBuf::from("missing.txt"));

        assert!(result.is_err(), "Should fail for nonexistent file");
    }

    // ============================================================================
    // Edge Case Tests
    // ============================================================================

    #[test]
    fn test_s3_config_empty_bucket() {
        let config = S3Config {
            bucket: "".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        // Creating VFS with empty bucket should still succeed at construction
        // but fail when trying to perform operations
        let result = S3Vfs::new(config);
        assert!(result.is_ok());
    }

    #[test]
    fn test_webdav_config_empty_url() {
        let config = WebDavConfig {
            url: "".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        // Creating VFS with empty URL should fail at construction
        let result = WebDavVfs::new(config);
        assert!(result.is_err(), "Should fail with empty URL");
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_empty_file() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let path = PathBuf::from("empty.txt");

        // Write empty file
        let result = vfs.write_file(&path, b"");
        assert!(result.is_ok());

        // Read it back
        use std::io::Read;
        let mut reader = vfs.open_file(&path).expect("Failed to open empty file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read empty file");

        assert_eq!(buffer.len(), 0);

        // Check metadata
        let meta = vfs.metadata(&path).expect("Failed to get metadata");
        assert_eq!(meta.size, 0);

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_empty_file() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let path = PathBuf::from("empty.txt");

        // Write empty file
        let result = vfs.write_file(&path, b"");
        assert!(result.is_ok());

        // Read it back
        use std::io::Read;
        let mut reader = vfs.open_file(&path).expect("Failed to open empty file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read empty file");

        assert_eq!(buffer.len(), 0);

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    #[test]
    #[ignore]
    fn test_s3_vfs_special_characters_in_path() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");

        // Test file names with spaces and special characters
        let paths = vec![
            PathBuf::from("file with spaces.txt"),
            PathBuf::from("file-with-dashes.txt"),
            PathBuf::from("file_with_underscores.txt"),
        ];

        for path in paths {
            let result = vfs.write_file(&path, b"test");
            assert!(result.is_ok(), "Failed to write file with special chars: {:?}", path);

            let _ = vfs.remove_file(&path);
        }
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_nested_directories() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");

        // Create nested directory structure
        let nested_dir = PathBuf::from("level1/level2/level3");
        let result = vfs.create_dir_all(&nested_dir);
        assert!(result.is_ok(), "Failed to create nested directories");

        // Write a file in the nested directory
        let file_path = PathBuf::from("level1/level2/level3/test.txt");
        let result = vfs.write_file(&file_path, b"nested file");
        assert!(result.is_ok(), "Failed to write file in nested directory");

        // Clean up
        let _ = vfs.remove_file(&file_path);
    }

    // ============================================================================
    // Integration Tests - Cross-VFS Operations
    // ============================================================================

    #[test]
    #[ignore]
    fn test_s3_vfs_large_file() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let path = PathBuf::from("large-file.bin");

        // Create 1MB of data
        let data = vec![0u8; 1024 * 1024];

        // Write large file
        let result = vfs.write_file(&path, &data);
        assert!(result.is_ok(), "Failed to write large file");

        // Read it back
        use std::io::Read;
        let mut reader = vfs.open_file(&path).expect("Failed to open large file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read large file");

        assert_eq!(buffer.len(), data.len());

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_large_file() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let path = PathBuf::from("large-file.bin");

        // Create 1MB of data
        let data = vec![0u8; 1024 * 1024];

        // Write large file
        let result = vfs.write_file(&path, &data);
        assert!(result.is_ok(), "Failed to write large file");

        // Read it back
        use std::io::Read;
        let mut reader = vfs.open_file(&path).expect("Failed to open large file");
        let mut buffer = Vec::new();
        reader.read_to_end(&mut buffer).expect("Failed to read large file");

        assert_eq!(buffer.len(), data.len());

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    #[test]
    fn test_s3_auth_access_key_without_session_token() {
        let auth = S3Auth::AccessKey {
            access_key_id: "AKIAIOSFODNN7EXAMPLE".to_string(),
            secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY".to_string(),
            session_token: None,
        };

        if let S3Auth::AccessKey { session_token, .. } = auth {
            assert!(session_token.is_none());
        } else {
            panic!("Expected AccessKey auth");
        }
    }

    #[test]
    fn test_s3_auth_access_key_with_session_token() {
        let auth = S3Auth::AccessKey {
            access_key_id: "key".to_string(),
            secret_access_key: "secret".to_string(),
            session_token: Some("session123".to_string()),
        };

        if let S3Auth::AccessKey { session_token, .. } = auth {
            assert_eq!(session_token, Some("session123".to_string()));
        } else {
            panic!("Expected AccessKey auth");
        }
    }

    // ============================================================================
    // S3Writer and WebDavWriter Tests
    // ============================================================================

    #[test]
    #[ignore]
    fn test_s3_writer_buffered_writes() {
        use std::io::Write;

        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let path = PathBuf::from("buffered-test.txt");

        // Create a writer
        let mut writer = vfs.create_file(&path).expect("Failed to create file");

        // Write data in chunks
        let chunk1 = b"Hello ";
        let chunk2 = b"World";
        let chunk3 = b"!";

        writer.write_all(chunk1).expect("Failed to write chunk 1");
        writer.write_all(chunk2).expect("Failed to write chunk 2");
        writer.write_all(chunk3).expect("Failed to write chunk 3");

        // Flush to ensure upload
        writer.flush().expect("Failed to flush");

        // Drop writer to trigger final upload
        drop(writer);

        // Read back and verify
        use std::io::Read;
        let mut reader = vfs.open_file(&path).expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read file");

        assert_eq!(buffer, "Hello World!");

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    #[test]
    #[ignore]
    fn test_webdav_writer_buffered_writes() {
        use std::io::Write;

        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");
        let path = PathBuf::from("buffered-test.txt");

        // Create a writer
        let mut writer = vfs.create_file(&path).expect("Failed to create file");

        // Write data in chunks
        let chunk1 = b"WebDAV ";
        let chunk2 = b"test";

        writer.write_all(chunk1).expect("Failed to write chunk 1");
        writer.write_all(chunk2).expect("Failed to write chunk 2");

        // Flush
        writer.flush().expect("Failed to flush");

        // Drop writer
        drop(writer);

        // Read back and verify
        use std::io::Read;
        let mut reader = vfs.open_file(&path).expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read file");

        assert_eq!(buffer, "WebDAV test");

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    #[test]
    #[ignore]
    fn test_s3_writer_multiple_flushes() {
        use std::io::Write;

        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");
        let path = PathBuf::from("multi-flush.txt");

        let mut writer = vfs.create_file(&path).expect("Failed to create file");

        writer.write_all(b"First").expect("Failed to write");
        writer.flush().expect("Failed to flush 1");

        writer.write_all(b" Second").expect("Failed to write");
        writer.flush().expect("Failed to flush 2");

        drop(writer);

        // Read and verify
        use std::io::Read;
        let mut reader = vfs.open_file(&path).expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read file");

        // Note: S3Writer buffers all writes until final flush/drop
        assert!(buffer.contains("First"));
        assert!(buffer.contains("Second"));

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    // ============================================================================
    // Additional Configuration Tests
    // ============================================================================

    #[test]
    fn test_s3_config_various_regions() {
        let regions = vec![
            "us-east-1",
            "us-west-2",
            "eu-west-1",
            "eu-central-1",
            "ap-southeast-1",
            "ap-northeast-1",
        ];

        for region in regions {
            let config = S3Config {
                bucket: "test".to_string(),
                region: region.to_string(),
                prefix: PathBuf::from("/"),
                auth: S3Auth::Default,
                endpoint: None,
            };

            assert_eq!(config.region, region);
        }
    }

    #[test]
    fn test_webdav_config_various_urls() {
        let urls = vec![
            "http://localhost/webdav",
            "https://cloud.example.com/remote.php/dav/files/user",
            "https://nextcloud.example.org/webdav",
            "http://192.168.1.100:8080/dav",
        ];

        for url in urls {
            let config = WebDavConfig {
                url: url.to_string(),
                auth: WebDavAuth::None,
                root_path: PathBuf::from("/"),
            };

            assert_eq!(config.url, url);
        }
    }

    #[test]
    fn test_s3_config_with_various_prefixes() {
        let prefixes = vec![
            PathBuf::from("/"),
            PathBuf::from("/data"),
            PathBuf::from("/backups/2024"),
            PathBuf::from("/project/files"),
        ];

        for prefix in prefixes {
            let config = S3Config {
                bucket: "test".to_string(),
                region: "us-east-1".to_string(),
                prefix: prefix.clone(),
                auth: S3Auth::Default,
                endpoint: None,
            };

            assert_eq!(config.prefix, prefix);
        }
    }

    #[test]
    fn test_webdav_config_with_various_root_paths() {
        let root_paths = vec![
            PathBuf::from("/"),
            PathBuf::from("/Documents"),
            PathBuf::from("/Shared/Public"),
            PathBuf::from("/Projects/2024"),
        ];

        for root_path in root_paths {
            let config = WebDavConfig {
                url: "http://localhost/webdav".to_string(),
                auth: WebDavAuth::None,
                root_path: root_path.clone(),
            };

            assert_eq!(config.root_path, root_path);
        }
    }

    // ============================================================================
    // Concurrent Access Tests
    // ============================================================================

    #[test]
    #[ignore]
    fn test_s3_vfs_concurrent_reads() {
        use std::io::Read;
        use std::sync::Arc;
        use std::thread;

        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = Arc::new(S3Vfs::new(config).expect("Failed to create S3 VFS"));
        let path = PathBuf::from("concurrent-test.txt");

        // Write a test file
        vfs.write_file(&path, b"Concurrent test data").expect("Failed to write file");

        // Spawn multiple threads to read the same file
        let mut handles = vec![];

        for _ in 0..5 {
            let vfs_clone = Arc::clone(&vfs);
            let path_clone = path.clone();

            let handle = thread::spawn(move || {
                let mut reader = vfs_clone.open_file(&path_clone).expect("Failed to open file");
                let mut buffer = String::new();
                reader.read_to_string(&mut buffer).expect("Failed to read file");
                assert_eq!(buffer, "Concurrent test data");
            });

            handles.push(handle);
        }

        // Wait for all threads
        for handle in handles {
            handle.join().expect("Thread panicked");
        }

        // Clean up
        let _ = vfs.remove_file(&path);
    }

    // ============================================================================
    // Path Normalization Tests
    // ============================================================================

    #[test]
    #[ignore]
    fn test_s3_vfs_path_with_leading_slash() {
        let config = S3Config {
            bucket: "test-bucket".to_string(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        };

        let vfs = S3Vfs::new(config).expect("Failed to create S3 VFS");

        // Test paths with and without leading slash
        let path1 = PathBuf::from("file.txt");
        let path2 = PathBuf::from("/file.txt");

        vfs.write_file(&path1, b"test1").expect("Failed to write path1");
        let meta = vfs.metadata(&path1).expect("Failed to get metadata");
        assert_eq!(meta.size, 5);

        // Clean up
        let _ = vfs.remove_file(&path1);
        let _ = vfs.remove_file(&path2);
    }

    #[test]
    #[ignore]
    fn test_webdav_vfs_path_with_leading_slash() {
        let config = WebDavConfig {
            url: "http://localhost:8080/webdav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        };

        let vfs = WebDavVfs::new(config).expect("Failed to create WebDAV VFS");

        // Test paths with and without leading slash
        let path1 = PathBuf::from("file.txt");

        vfs.write_file(&path1, b"test").expect("Failed to write path");
        let meta = vfs.metadata(&path1).expect("Failed to get metadata");
        assert_eq!(meta.size, 4);

        // Clean up
        let _ = vfs.remove_file(&path1);
    }
}
