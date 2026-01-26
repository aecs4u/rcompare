#[cfg(test)]
mod tests {
    use crate::vfs::{
        CompressedFileVfs, TarVfs, WritableCompressedFileVfs, WritableZipVfs, ZipVfs,
    };
    use rcompare_common::Vfs;
    use std::fs;
    use std::io::{Read, Write};
    use std::path::PathBuf;
    use tempfile::TempDir;

    // ============================================================================
    // ZIP VFS Tests (Read-Only)
    // ============================================================================

    #[test]
    fn test_zip_vfs_creation() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("test.zip");

        // Create a simple ZIP file
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::FileOptions::default();

        zip.start_file("test.txt", options)
            .expect("Failed to start file");
        zip.write_all(b"Hello, ZIP!").expect("Failed to write");
        zip.finish().expect("Failed to finish ZIP");

        // Create VFS
        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");
        let instance_id = vfs.instance_id();

        assert!(instance_id.starts_with("zip:"));
    }

    #[test]
    fn test_zip_vfs_nonexistent_file() {
        let result = ZipVfs::new(PathBuf::from("/nonexistent/file.zip"));
        assert!(result.is_err(), "Should fail for nonexistent file");
    }

    #[test]
    fn test_zip_vfs_read_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("test.zip");

        // Create ZIP with content
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::FileOptions::default();

        zip.start_file("data.txt", options)
            .expect("Failed to start file");
        zip.write_all(b"Test data content")
            .expect("Failed to write");
        zip.finish().expect("Failed to finish ZIP");

        // Read through VFS
        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");
        let mut reader = vfs
            .open_file(&PathBuf::from("data.txt"))
            .expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "Test data content");
    }

    #[test]
    fn test_zip_vfs_read_dir() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("test.zip");

        // Create ZIP with multiple files
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::FileOptions::default();

        zip.start_file("file1.txt", options)
            .expect("Failed to start file");
        zip.write_all(b"File 1").expect("Failed to write");

        zip.start_file("file2.txt", options)
            .expect("Failed to start file");
        zip.write_all(b"File 2").expect("Failed to write");

        zip.finish().expect("Failed to finish ZIP");

        // Read directory
        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");
        let entries = vfs
            .read_dir(&PathBuf::from(""))
            .expect("Failed to read dir");

        assert_eq!(entries.len(), 2);
        let names: Vec<String> = entries
            .iter()
            .map(|e| e.path.file_name().unwrap().to_string_lossy().to_string())
            .collect();

        assert!(names.contains(&"file1.txt".to_string()));
        assert!(names.contains(&"file2.txt".to_string()));
    }

    #[test]
    fn test_zip_vfs_metadata() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("test.zip");

        // Create ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::FileOptions::default();

        let content = b"Test content for metadata";
        zip.start_file("meta.txt", options)
            .expect("Failed to start file");
        zip.write_all(content).expect("Failed to write");
        zip.finish().expect("Failed to finish ZIP");

        // Get metadata
        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");
        let meta = vfs
            .metadata(&PathBuf::from("meta.txt"))
            .expect("Failed to get metadata");

        assert_eq!(meta.size, content.len() as u64);
        assert!(!meta.is_dir);
    }

    #[test]
    fn test_zip_vfs_capabilities() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("test.zip");

        // Create minimal ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");
        let caps = vfs.capabilities();

        assert!(caps.read, "ZIP should support reading");
        assert!(!caps.write, "ZIP (read-only) should not support writing");
        assert!(!caps.delete, "ZIP (read-only) should not support deletion");
    }

    #[test]
    fn test_zip_vfs_write_fails() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("test.zip");

        // Create minimal ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");

        // Try to write - should fail
        let result = vfs.write_file(&PathBuf::from("new.txt"), b"content");
        assert!(result.is_err(), "Write should fail on read-only ZIP");
    }

    // ============================================================================
    // Writable ZIP VFS Tests
    // ============================================================================

    #[test]
    fn test_writable_zip_vfs_creation() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("writable.zip");

        // Create minimal ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs = WritableZipVfs::new(zip_path).expect("Failed to create WritableZipVfs");
        assert!(vfs.instance_id().starts_with("zip-rw:"));
    }

    #[test]
    fn test_writable_zip_vfs_write_and_read() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("writable.zip");

        // Create minimal ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs =
            WritableZipVfs::new(zip_path.clone()).expect("Failed to create WritableZipVfs");

        // Write a file
        vfs.write_file(&PathBuf::from("new.txt"), b"New content")
            .expect("Failed to write");

        // Flush changes
        vfs.flush().expect("Failed to flush");

        // Read back from new instance
        let read_vfs = ZipVfs::new(zip_path).expect("Failed to open ZIP");
        let mut reader = read_vfs
            .open_file(&PathBuf::from("new.txt"))
            .expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "New content");
    }

    #[test]
    fn test_writable_zip_vfs_capabilities() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("writable.zip");

        // Create minimal ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs = WritableZipVfs::new(zip_path).expect("Failed to create WritableZipVfs");
        let caps = vfs.capabilities();

        assert!(caps.read, "Writable ZIP should support reading");
        assert!(caps.write, "Writable ZIP should support writing");
        assert!(caps.delete, "Writable ZIP should support deletion");
    }

    // ============================================================================
    // TAR VFS Tests (Read-Only)
    // ============================================================================

    #[test]
    fn test_tar_vfs_creation() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let tar_path = temp_dir.path().join("test.tar");

        // Create a simple TAR file
        let file = fs::File::create(&tar_path).expect("Failed to create file");
        let mut tar = tar::Builder::new(file);

        let data = b"Hello, TAR!";
        let mut header = tar::Header::new_gnu();
        header.set_size(data.len() as u64);
        header.set_cksum();
        tar.append_data(&mut header, "test.txt", &data[..])
            .expect("Failed to append");
        tar.finish().expect("Failed to finish TAR");

        // Create VFS
        let vfs = TarVfs::new(tar_path).expect("Failed to create TarVfs");
        assert!(vfs.instance_id().starts_with("tar:"));
    }

    #[test]
    fn test_tar_vfs_read_file() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let tar_path = temp_dir.path().join("test.tar");

        // Create TAR with content
        let file = fs::File::create(&tar_path).expect("Failed to create file");
        let mut tar = tar::Builder::new(file);

        let data = b"TAR content";
        let mut header = tar::Header::new_gnu();
        header.set_size(data.len() as u64);
        header.set_cksum();
        tar.append_data(&mut header, "data.txt", &data[..])
            .expect("Failed to append");
        tar.finish().expect("Failed to finish TAR");

        // Read through VFS
        let vfs = TarVfs::new(tar_path).expect("Failed to create TarVfs");
        let mut reader = vfs
            .open_file(&PathBuf::from("data.txt"))
            .expect("Failed to open file");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "TAR content");
    }

    #[test]
    fn test_tar_vfs_capabilities() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let tar_path = temp_dir.path().join("test.tar");

        // Create minimal TAR
        let file = fs::File::create(&tar_path).expect("Failed to create file");
        let mut tar = tar::Builder::new(file);
        tar.finish().expect("Failed to finish TAR");

        let vfs = TarVfs::new(tar_path).expect("Failed to create TarVfs");
        let caps = vfs.capabilities();

        assert!(caps.read, "TAR should support reading");
        assert!(!caps.write, "TAR (read-only) should not support writing");
    }

    // ============================================================================
    // Compressed File VFS Tests
    // ============================================================================

    #[test]
    fn test_compressed_file_vfs_gzip() {
        use flate2::write::GzEncoder;
        use flate2::Compression;

        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let gz_path = temp_dir.path().join("test.txt.gz");

        // Create gzipped file
        let file = fs::File::create(&gz_path).expect("Failed to create file");
        let mut encoder = GzEncoder::new(file, Compression::default());
        encoder
            .write_all(b"Compressed content")
            .expect("Failed to write");
        encoder.finish().expect("Failed to finish");

        // Read through VFS (compression type detected from .gz extension)
        let vfs = CompressedFileVfs::new(gz_path).expect("Failed to create CompressedFileVfs");

        let mut reader = vfs
            .open_file(&PathBuf::from("test.txt"))
            .expect("Failed to open");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "Compressed content");
    }

    #[test]
    fn test_compressed_file_vfs_bzip2() {
        use bzip2::write::BzEncoder;
        use bzip2::Compression;

        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let bz2_path = temp_dir.path().join("test.txt.bz2");

        // Create bzip2 file
        let file = fs::File::create(&bz2_path).expect("Failed to create file");
        let mut encoder = BzEncoder::new(file, Compression::default());
        encoder
            .write_all(b"Bzip2 content")
            .expect("Failed to write");
        encoder.finish().expect("Failed to finish");

        // Read through VFS (compression type detected from .bz2 extension)
        let vfs = CompressedFileVfs::new(bz2_path).expect("Failed to create CompressedFileVfs");

        let mut reader = vfs
            .open_file(&PathBuf::from("test.txt"))
            .expect("Failed to open");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "Bzip2 content");
    }

    #[test]
    fn test_compressed_file_vfs_xz() {
        use xz2::write::XzEncoder;

        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let xz_path = temp_dir.path().join("test.txt.xz");

        // Create XZ file
        let file = fs::File::create(&xz_path).expect("Failed to create file");
        let mut encoder = XzEncoder::new(file, 6);
        encoder.write_all(b"XZ content").expect("Failed to write");
        encoder.finish().expect("Failed to finish");

        // Read through VFS (compression type detected from .xz extension)
        let vfs = CompressedFileVfs::new(xz_path).expect("Failed to create CompressedFileVfs");

        let mut reader = vfs
            .open_file(&PathBuf::from("test.txt"))
            .expect("Failed to open");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "XZ content");
    }

    #[test]
    fn test_compressed_file_vfs_capabilities() {
        use flate2::write::GzEncoder;
        use flate2::Compression;

        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let gz_path = temp_dir.path().join("test.gz");

        let file = fs::File::create(&gz_path).expect("Failed to create file");
        let mut encoder = GzEncoder::new(file, Compression::default());
        encoder.write_all(b"test").expect("Failed to write");
        encoder.finish().expect("Failed to finish");

        let vfs = CompressedFileVfs::new(gz_path).expect("Failed to create CompressedFileVfs");
        let caps = vfs.capabilities();

        assert!(caps.read, "Compressed file should support reading");
        assert!(
            !caps.write,
            "Compressed file (read-only) should not support writing"
        );
    }

    // ============================================================================
    // Writable Compressed File VFS Tests
    // ============================================================================

    #[test]
    fn test_writable_compressed_file_vfs_gzip() {
        use flate2::read::GzDecoder;

        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let gz_path = temp_dir.path().join("output.txt.gz");

        // Write through VFS (compression type detected from .gz extension)
        let vfs = WritableCompressedFileVfs::new(gz_path.clone())
            .expect("Failed to create WritableCompressedFileVfs");

        vfs.write_file(&PathBuf::from("output.txt"), b"Writable content")
            .expect("Failed to write");
        vfs.flush().expect("Failed to flush");

        // Read back directly
        let file = fs::File::open(&gz_path).expect("Failed to open");
        let mut decoder = GzDecoder::new(file);
        let mut buffer = String::new();
        decoder.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "Writable content");
    }

    #[test]
    fn test_writable_compressed_file_vfs_capabilities() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let gz_path = temp_dir.path().join("output.gz");

        let vfs = WritableCompressedFileVfs::new(gz_path)
            .expect("Failed to create WritableCompressedFileVfs");
        let caps = vfs.capabilities();

        assert!(
            caps.write,
            "Writable compressed file should support writing"
        );
        assert!(caps.read, "Writable compressed file should support reading");
    }

    // ============================================================================
    // Edge Cases and Error Handling
    // ============================================================================

    #[test]
    fn test_zip_vfs_empty_archive() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("empty.zip");

        // Create empty ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");
        let entries = vfs
            .read_dir(&PathBuf::from(""))
            .expect("Failed to read dir");

        assert_eq!(entries.len(), 0);
    }

    #[test]
    fn test_zip_vfs_nested_directories() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("nested.zip");

        // Create ZIP with nested structure
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::FileOptions::default();

        zip.add_directory("dir1/", options)
            .expect("Failed to add dir");
        zip.start_file("dir1/file.txt", options)
            .expect("Failed to start file");
        zip.write_all(b"Nested file").expect("Failed to write");

        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");

        // Read file from nested directory
        let mut reader = vfs
            .open_file(&PathBuf::from("dir1/file.txt"))
            .expect("Failed to open");
        let mut buffer = String::new();
        reader.read_to_string(&mut buffer).expect("Failed to read");

        assert_eq!(buffer, "Nested file");
    }

    #[test]
    fn test_zip_vfs_file_not_found() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let zip_path = temp_dir.path().join("test.zip");

        // Create minimal ZIP
        let file = fs::File::create(&zip_path).expect("Failed to create file");
        let mut zip = zip::ZipWriter::new(file);
        let _ = zip.finish().expect("Failed to finish ZIP");

        let vfs = ZipVfs::new(zip_path).expect("Failed to create ZipVfs");

        let result = vfs.open_file(&PathBuf::from("nonexistent.txt"));
        assert!(result.is_err(), "Should fail for nonexistent file");

        let result = vfs.metadata(&PathBuf::from("missing.txt"));
        assert!(result.is_err(), "Should fail for nonexistent file");
    }

    #[test]
    fn test_tar_vfs_empty_archive() {
        let temp_dir = TempDir::new().expect("Failed to create temp dir");
        let tar_path = temp_dir.path().join("empty.tar");

        // Create empty TAR
        let file = fs::File::create(&tar_path).expect("Failed to create file");
        let mut tar = tar::Builder::new(file);
        tar.finish().expect("Failed to finish TAR");

        let vfs = TarVfs::new(tar_path).expect("Failed to create TarVfs");
        let entries = vfs
            .read_dir(&PathBuf::from(""))
            .expect("Failed to read dir");

        assert_eq!(entries.len(), 0);
    }
}
