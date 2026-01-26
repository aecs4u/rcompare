use filetime::{set_file_mtime, FileTime};
use std::fs;
#[cfg(unix)]
use std::os::unix::fs as unix_fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use tempfile::TempDir;

/// Helper struct to manage test directories
struct TestFixture {
    _temp_dir: TempDir,
    left_dir: PathBuf,
    right_dir: PathBuf,
}

impl TestFixture {
    /// Create a new test fixture with left and right directories
    fn new() -> Self {
        let temp_dir = TempDir::new().expect("Failed to create temp directory");
        let left_dir = temp_dir.path().join("left");
        let right_dir = temp_dir.path().join("right");

        fs::create_dir(&left_dir).expect("Failed to create left dir");
        fs::create_dir(&right_dir).expect("Failed to create right dir");

        TestFixture {
            _temp_dir: temp_dir,
            left_dir,
            right_dir,
        }
    }

    /// Create a file with content in the left directory
    fn create_left_file<P: AsRef<Path>>(&self, path: P, content: &str) -> PathBuf {
        self.create_file(&self.left_dir, path, content)
    }

    /// Create a file with content in the right directory
    fn create_right_file<P: AsRef<Path>>(&self, path: P, content: &str) -> PathBuf {
        self.create_file(&self.right_dir, path, content)
    }

    /// Create a file with content in the specified base directory
    fn create_file<P: AsRef<Path>>(&self, base: &Path, path: P, content: &str) -> PathBuf {
        let file_path = base.join(path.as_ref());

        // Create parent directories if needed
        if let Some(parent) = file_path.parent() {
            fs::create_dir_all(parent).expect("Failed to create parent directories");
        }

        fs::write(&file_path, content).expect("Failed to write file");
        file_path
    }

    /// Create a directory in the left side
    #[allow(dead_code)]
    fn create_left_dir<P: AsRef<Path>>(&self, path: P) -> PathBuf {
        let dir_path = self.left_dir.join(path.as_ref());
        fs::create_dir_all(&dir_path).expect("Failed to create directory");
        dir_path
    }

    /// Create a directory in the right side
    #[allow(dead_code)]
    fn create_right_dir<P: AsRef<Path>>(&self, path: P) -> PathBuf {
        let dir_path = self.right_dir.join(path.as_ref());
        fs::create_dir_all(&dir_path).expect("Failed to create directory");
        dir_path
    }

    /// Set modification time for a file
    #[allow(dead_code)]
    fn set_mtime<P: AsRef<Path>>(&self, path: P, mtime: FileTime) {
        set_file_mtime(path, mtime).expect("Failed to set mtime");
    }

    /// Get the left directory path
    fn left(&self) -> &Path {
        &self.left_dir
    }

    /// Get the right directory path
    fn right(&self) -> &Path {
        &self.right_dir
    }
}

/// Helper to run the CLI binary
fn run_cli(args: &[&str]) -> std::process::Output {
    let exe = env!("CARGO_BIN_EXE_rcompare_cli");
    let config_dir = TempDir::new().expect("Failed to create config dir");
    let cache_dir = TempDir::new().expect("Failed to create cache dir");
    Command::new(exe)
        .args(args)
        .env("XDG_CONFIG_HOME", config_dir.path())
        .env("XDG_CACHE_HOME", cache_dir.path())
        .env("APPDATA", config_dir.path())
        .env("LOCALAPPDATA", cache_dir.path())
        .env("HOME", config_dir.path())
        .output()
        .expect("Failed to execute command")
}

/// Helper to run CLI and expect success
fn run_cli_success(args: &[&str]) -> std::process::Output {
    let output = run_cli(args);
    if !output.status.success() {
        eprintln!("STDOUT:\n{}", String::from_utf8_lossy(&output.stdout));
        eprintln!("STDERR:\n{}", String::from_utf8_lossy(&output.stderr));
        panic!("Command failed with status: {}", output.status);
    }
    output
}

#[test]
fn test_identical_directories() {
    let fixture = TestFixture::new();

    // Create identical files in both directories
    fixture.create_left_file("file1.txt", "Hello, world!");
    fixture.create_right_file("file1.txt", "Hello, world!");

    fixture.create_left_file("file2.txt", "Test content");
    fixture.create_right_file("file2.txt", "Test content");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Identical:"));
    assert!(stdout.contains("file1.txt"));
    assert!(stdout.contains("file2.txt"));
}

#[test]
fn test_different_files() {
    let fixture = TestFixture::new();

    // Create files with different content
    fixture.create_left_file("file.txt", "Left content");
    fixture.create_right_file("file.txt", "Right content");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Different:"));
    assert!(stdout.contains("file.txt"));
}

#[test]
fn test_orphan_left() {
    let fixture = TestFixture::new();

    // Create file only in left directory
    fixture.create_left_file("only_left.txt", "Only on left");
    fixture.create_right_file("common.txt", "Common file");
    fixture.create_left_file("common.txt", "Common file");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Left only:"));
    assert!(stdout.contains("only_left.txt"));
}

#[test]
fn test_orphan_right() {
    let fixture = TestFixture::new();

    // Create file only in right directory
    fixture.create_right_file("only_right.txt", "Only on right");
    fixture.create_right_file("common.txt", "Common file");
    fixture.create_left_file("common.txt", "Common file");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Right only:"));
    assert!(stdout.contains("only_right.txt"));
}

#[test]
fn test_nested_directories() {
    let fixture = TestFixture::new();

    // Create nested directory structures
    fixture.create_left_file("dir1/subdir/file.txt", "Content");
    fixture.create_right_file("dir1/subdir/file.txt", "Content");

    fixture.create_left_file("dir2/file.txt", "Left only");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("dir1"));
    assert!(stdout.contains("dir2"));
}

#[test]
fn test_diff_only_flag() {
    let fixture = TestFixture::new();

    // Create identical and different files
    fixture.create_left_file("same.txt", "Same content");
    fixture.create_right_file("same.txt", "Same content");

    fixture.create_left_file("different.txt", "Left");
    fixture.create_right_file("different.txt", "Right");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--diff-only",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);

    // Should show different file
    assert!(stdout.contains("different.txt"));

    // Should NOT show same file in the listing (but may appear in summary)
    let lines: Vec<&str> = stdout.lines().collect();
    let result_lines: Vec<&str> = lines
        .iter()
        .skip_while(|l| !l.contains("Comparison Results"))
        .take_while(|l| !l.contains("Summary"))
        .copied()
        .collect();

    let result_text = result_lines.join("\n");
    assert!(!result_text.contains("same.txt") || !result_text.contains("=="));
}

#[test]
fn test_json_output() {
    let fixture = TestFixture::new();

    fixture.create_left_file("file1.txt", "Content 1");
    fixture.create_right_file("file1.txt", "Content 1");

    fixture.create_left_file("file2.txt", "Left");
    fixture.create_right_file("file2.txt", "Right");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--json",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);

    // Parse JSON to verify it's valid
    let json: serde_json::Value =
        serde_json::from_str(&stdout).expect("Output should be valid JSON");

    // Verify structure
    assert!(json.get("left").is_some());
    assert!(json.get("right").is_some());
    assert!(json.get("summary").is_some());
    assert!(json.get("entries").is_some());

    // Verify summary contains counts
    let summary = json.get("summary").unwrap();
    assert!(summary.get("total").is_some());
    assert!(summary.get("same").is_some());
    assert!(summary.get("different").is_some());
}

#[test]
fn test_json_output_with_diff_only() {
    let fixture = TestFixture::new();

    fixture.create_left_file("same.txt", "Same");
    fixture.create_right_file("same.txt", "Same");

    fixture.create_left_file("different.txt", "Left");
    fixture.create_right_file("different.txt", "Right");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--json",
        "--diff-only",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    let json: serde_json::Value =
        serde_json::from_str(&stdout).expect("Output should be valid JSON");

    let entries = json.get("entries").unwrap().as_array().unwrap();

    // Should only contain the different file
    assert_eq!(entries.len(), 1);
    assert!(entries[0]
        .get("path")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("different.txt"));
}

#[test]
fn test_nonexistent_left_path() {
    let fixture = TestFixture::new();

    let output = run_cli(&[
        "scan",
        "/nonexistent/path/left",
        fixture.right().to_str().unwrap(),
    ]);

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("does not exist") || stderr.contains("Left path"));
}

#[test]
fn test_nonexistent_right_path() {
    let fixture = TestFixture::new();

    let output = run_cli(&[
        "scan",
        fixture.left().to_str().unwrap(),
        "/nonexistent/path/right",
    ]);

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("does not exist") || stderr.contains("Right path"));
}

#[test]
fn test_unsupported_archive_path() {
    let fixture = TestFixture::new();
    let temp = TempDir::new().expect("Failed to create temp dir");
    let left_file = temp.path().join("left.txt");
    fs::write(&left_file, "not an archive").unwrap();

    let output = run_cli(&[
        "scan",
        left_file.to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("supported archive") || stderr.contains("not a directory"));
}

#[test]
fn test_ignore_patterns() {
    let fixture = TestFixture::new();

    // Create files that should be ignored
    fixture.create_left_file("test.log", "Log file");
    fixture.create_right_file("test.log", "Log file");

    fixture.create_left_file("file.txt", "Text file");
    fixture.create_right_file("file.txt", "Text file");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--ignore",
        "*.log",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);

    // Should include .txt file
    assert!(stdout.contains("file.txt"));

    // Should not include .log file (check in the results section, not summary)
    let lines: Vec<&str> = stdout.lines().collect();
    let result_lines: Vec<&str> = lines
        .iter()
        .skip_while(|l| !l.contains("Comparison Results"))
        .take_while(|l| !l.contains("Summary"))
        .copied()
        .collect();

    let result_text = result_lines.join("\n");
    assert!(!result_text.contains("test.log"));
}

#[test]
fn test_multiple_ignore_patterns() {
    let fixture = TestFixture::new();

    fixture.create_left_file("test.log", "Log");
    fixture.create_left_file("temp.tmp", "Temp");
    fixture.create_left_file("file.txt", "Text");

    fixture.create_right_file("test.log", "Log");
    fixture.create_right_file("temp.tmp", "Temp");
    fixture.create_right_file("file.txt", "Text");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--ignore",
        "*.log",
        "--ignore",
        "*.tmp",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);

    // Extract result section
    let lines: Vec<&str> = stdout.lines().collect();
    let result_lines: Vec<&str> = lines
        .iter()
        .skip_while(|l| !l.contains("Comparison Results"))
        .take_while(|l| !l.contains("Summary"))
        .copied()
        .collect();

    let result_text = result_lines.join("\n");

    assert!(result_text.contains("file.txt"));
    assert!(!result_text.contains("test.log"));
    assert!(!result_text.contains("temp.tmp"));
}

#[test]
fn test_empty_directories() {
    let fixture = TestFixture::new();

    // Both directories are empty (just created)

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    // Empty directories still have the directory entry itself
    assert!(stdout.contains("Total entries:") || stdout.contains("Identical:"));
}

#[test]
fn test_verify_hashes_flag() {
    let fixture = TestFixture::new();

    // Create files with same size but different content
    fixture.create_left_file("file.txt", "aaaa");
    fixture.create_right_file("file.txt", "bbbb");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--verify-hashes",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);

    // With hash verification, these should be detected as different
    assert!(stdout.contains("Different:") && stdout.contains("1"));
}

#[test]
fn test_cache_dir_option() {
    let fixture = TestFixture::new();
    let cache_dir = TempDir::new().expect("Failed to create cache dir");

    fixture.create_left_file("file.txt", "Content");
    fixture.create_right_file("file.txt", "Content");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--cache-dir",
        cache_dir.path().to_str().unwrap(),
    ]);

    assert!(output.status.success());

    // Cache directory message goes to stderr, but we can verify success by checking stdout has results
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Comparison Results") || stdout.contains("Summary"));
}

#[test]
fn test_summary_counts() {
    let fixture = TestFixture::new();

    // Create a mix of files
    fixture.create_left_file("same.txt", "Same");
    fixture.create_right_file("same.txt", "Same");

    fixture.create_left_file("different.txt", "Left");
    fixture.create_right_file("different.txt", "Right");

    fixture.create_left_file("left_only.txt", "Left only");
    fixture.create_right_file("right_only.txt", "Right only");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);

    // Verify summary contains expected counts
    // Note: Total includes the root directory entry as well
    assert!(stdout.contains("Total entries:"));
    assert!(stdout.contains("Identical:") && stdout.contains("1"));
    assert!(stdout.contains("Different:") && stdout.contains("1"));
    assert!(stdout.contains("Left only:") && stdout.contains("1"));
    assert!(stdout.contains("Right only:") && stdout.contains("1"));
}

#[test]
fn test_help_flag() {
    let output = run_cli(&["--help"]);

    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("High-performance file and directory comparison"));
    assert!(stdout.contains("scan"));
}

#[test]
fn test_version_flag() {
    let output = run_cli(&["--version"]);

    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("rcompare"));
}

#[test]
fn test_scan_help() {
    let output = run_cli(&["scan", "--help"]);

    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Left directory path"));
    assert!(stdout.contains("Right directory path"));
    assert!(stdout.contains("--ignore"));
    assert!(stdout.contains("--json"));
}

#[test]
fn test_no_color_flag() {
    let fixture = TestFixture::new();

    fixture.create_left_file("file.txt", "Left");
    fixture.create_right_file("file.txt", "Right");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--no-color",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    // Should not contain ANSI escape codes
    assert!(!stdout.contains("\x1b["));
}

#[test]
#[cfg(unix)]
fn test_symlink_dir_not_followed_by_default() {
    let fixture = TestFixture::new();
    let target = TempDir::new().expect("Failed to create target dir");

    fs::write(target.path().join("linked.txt"), "Linked content").unwrap();
    unix_fs::symlink(target.path(), fixture.left().join("linked_dir"))
        .expect("Failed to create symlink");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(!stdout.contains("linked_dir/linked.txt"));
}

#[test]
#[cfg(unix)]
fn test_follow_symlinks_flag_includes_target() {
    let fixture = TestFixture::new();
    let target = TempDir::new().expect("Failed to create target dir");

    fs::write(target.path().join("linked.txt"), "Linked content").unwrap();
    unix_fs::symlink(target.path(), fixture.left().join("linked_dir"))
        .expect("Failed to create symlink");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--follow-symlinks",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("linked_dir/linked.txt"));
}

#[test]
fn test_default_no_color_when_piped() {
    let fixture = TestFixture::new();

    fixture.create_left_file("file.txt", "Left");
    fixture.create_right_file("file.txt", "Right");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(!stdout.contains("\x1b["));
}

#[test]
fn test_deeply_nested_structure() {
    let fixture = TestFixture::new();

    // Create deeply nested directories
    fixture.create_left_file("a/b/c/d/e/f/file.txt", "Content");
    fixture.create_right_file("a/b/c/d/e/f/file.txt", "Content");

    fixture.create_left_file("a/b/c/d/e/f/different.txt", "Left");
    fixture.create_right_file("a/b/c/d/e/f/different.txt", "Right");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("file.txt"));
    assert!(stdout.contains("different.txt"));
}

#[test]
fn test_special_characters_in_filenames() {
    let fixture = TestFixture::new();

    // Create files with special characters
    fixture.create_left_file("file with spaces.txt", "Content");
    fixture.create_right_file("file with spaces.txt", "Content");

    fixture.create_left_file("file-with-dashes.txt", "Content");
    fixture.create_right_file("file-with-dashes.txt", "Content");

    fixture.create_left_file("file_with_underscores.txt", "Content");
    fixture.create_right_file("file_with_underscores.txt", "Content");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("file with spaces.txt"));
    assert!(stdout.contains("file-with-dashes.txt"));
    assert!(stdout.contains("file_with_underscores.txt"));
}

#[test]
fn test_binary_file_comparison() {
    let fixture = TestFixture::new();

    // Create binary files
    let left_path = fixture.left_dir.join("binary.bin");
    let right_path = fixture.right_dir.join("binary.bin");

    let binary_data: Vec<u8> = (0..256).map(|i| i as u8).collect();
    fs::write(&left_path, &binary_data).unwrap();
    fs::write(&right_path, &binary_data).unwrap();

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("binary.bin"));
    assert!(stdout.contains("Identical:"));
}

#[test]
fn test_large_number_of_files() {
    let fixture = TestFixture::new();

    // Create many files
    for i in 0..50 {
        let content = format!("Content {}", i);
        fixture.create_left_file(format!("file_{:03}.txt", i), &content);
        fixture.create_right_file(format!("file_{:03}.txt", i), &content);
    }

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    // Should report many files
    assert!(stdout.contains("Total entries:"));
    assert!(stdout.contains("Identical:"));
}

#[test]
fn test_json_structure_complete() {
    let fixture = TestFixture::new();

    fixture.create_left_file("test.txt", "Content");
    fixture.create_right_file("test.txt", "Content");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--json",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    let json: serde_json::Value = serde_json::from_str(&stdout).expect("Valid JSON");

    // Verify all required fields exist
    assert!(json.get("left").is_some());
    assert!(json.get("right").is_some());
    assert!(json.get("summary").is_some());
    assert!(json.get("entries").is_some());

    let summary = json.get("summary").unwrap();
    assert!(summary.get("total").is_some());
    assert!(summary.get("same").is_some());
    assert!(summary.get("different").is_some());
    assert!(summary.get("orphan_left").is_some());
    assert!(summary.get("orphan_right").is_some());
    assert!(summary.get("unchecked").is_some());

    // Check entry structure
    let entries = json.get("entries").unwrap().as_array().unwrap();
    assert!(!entries.is_empty());

    let entry = &entries[0];
    assert!(entry.get("path").is_some());
    assert!(entry.get("status").is_some());
}

#[test]
fn test_json_entry_details() {
    let fixture = TestFixture::new();

    fixture.create_left_file("file.txt", "Content");
    fixture.create_right_file("file.txt", "Content");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--json",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    let json: serde_json::Value = serde_json::from_str(&stdout).expect("Valid JSON");

    let entries = json.get("entries").unwrap().as_array().unwrap();

    // Find the file entry
    let file_entry = entries.iter().find(|e| {
        e.get("path")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("file.txt")
    });

    assert!(file_entry.is_some());
    let entry = file_entry.unwrap();

    // Check left side details
    let left = entry.get("left").unwrap();
    assert!(left.get("size").is_some());
    assert!(left.get("modified_unix").is_some());
    assert!(left.get("is_dir").is_some());
    assert!(!left.get("is_dir").unwrap().as_bool().unwrap());

    // Check right side details
    let right = entry.get("right").unwrap();
    assert!(right.get("size").is_some());
}

#[test]
fn test_missing_subcommand() {
    let output = run_cli(&[]);

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("Usage:") || stderr.contains("subcommand"));
}

#[test]
fn test_conflicting_verify_hash_options() {
    let fixture = TestFixture::new();
    fixture.create_left_file("test.txt", "Test");
    fixture.create_right_file("test.txt", "Test");

    // --verify-hashes and --no-verify-hashes should conflict
    let output = run_cli(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--verify-hashes",
        "--no-verify-hashes",
    ]);

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("conflict") || stderr.contains("cannot be used with"));
}

#[test]
fn test_no_verify_hashes_flag() {
    let fixture = TestFixture::new();

    // Create files with same size and mtime but different content
    let left_path = fixture.create_left_file("same_meta.txt", "aaaa");
    let right_path = fixture.create_right_file("same_meta.txt", "bbbb");

    // Set same mtime
    let mtime = FileTime::from_unix_time(1700000000, 0);
    set_file_mtime(&left_path, mtime).unwrap();
    set_file_mtime(&right_path, mtime).unwrap();

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--no-verify-hashes",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    // Without hash verification, files with same size/mtime appear identical
    // Count should be 1 (one file on each side, appearing identical)
    assert!(stdout.contains("Identical:") && stdout.contains("1"));
}

#[test]
fn test_right_gitignore_ignored() {
    let fixture = TestFixture::new();

    fixture.create_right_file(".gitignore", "skip.txt\n");
    fixture.create_right_file("skip.txt", "Skip me");

    let output = run_cli_success(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);

    // .gitignore file itself should appear (not ignored)
    assert!(stdout.contains(".gitignore"));

    // skip.txt should be ignored by gitignore and not appear in results
    assert!(!stdout.contains("skip.txt"));

    // Should show only 1 right-only file (.gitignore)
    assert!(stdout.contains("Right only:") && stdout.contains("1"));
}
