#![allow(
    clippy::uninlined_format_args,
    clippy::unused_self,
    clippy::unwrap_used,
    clippy::use_self
)]
// Test fixtures deliberately fail fast at the operation that could not be prepared.

use filetime::{set_file_mtime, FileTime};
use std::fs;
#[cfg(unix)]
use std::os::unix::fs as unix_fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
#[cfg(unix)]
use std::thread;
#[cfg(unix)]
use std::time::{Duration, Instant};
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

/// Helper to run CLI and expect it to complete without error.
/// The CLI exits with code 0 (all identical) or 2 (differences found).
/// Both are considered success; only non-{0,2} codes indicate errors.
fn run_cli_success(args: &[&str]) -> std::process::Output {
    let output = run_cli(args);
    let code = output.status.code().unwrap_or(-1);
    if code != 0 && code != 2 {
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
        "--verify-hashes",
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
    assert_eq!(json["schema_version"], "2.0.0");
    assert_eq!(json["command"], "scan");
    assert!(json["data"].get("left").is_some());
    assert!(json["data"].get("right").is_some());
    assert!(json.get("summary").is_some());
    assert!(json["data"].get("entries").is_some());

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
        "--verify-hashes",
    ]);

    let stdout = String::from_utf8_lossy(&output.stdout);
    let json: serde_json::Value =
        serde_json::from_str(&stdout).expect("Output should be valid JSON");

    let entries = json["data"]["entries"].as_array().unwrap();

    // Should only contain the different file
    assert_eq!(entries.len(), 1, "diff-only entries: {entries:#?}");
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
        "--verify-hashes",
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
    assert!(json["data"].get("left").is_some());
    assert!(json["data"].get("right").is_some());
    assert!(json.get("summary").is_some());
    assert!(json["data"].get("entries").is_some());

    let summary = json.get("summary").unwrap();
    assert!(summary.get("total").is_some());
    assert!(summary.get("same").is_some());
    assert!(summary.get("different").is_some());
    assert!(summary.get("orphan_left").is_some());
    assert!(summary.get("orphan_right").is_some());
    assert!(summary.get("unchecked").is_some());

    // Check entry structure
    let entries = json["data"]["entries"].as_array().unwrap();
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

    let entries = json["data"]["entries"].as_array().unwrap();

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

#[test]
fn test_copy_command_mutates_selected_file() {
    let fixture = TestFixture::new();
    fixture.create_left_file("nested/file.txt", "copied");

    let output = run_cli(&[
        "copy",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--path",
        "nested/file.txt",
        "--json",
    ]);

    assert!(output.status.success(), "copy failed: {:?}", output);
    let report: serde_json::Value =
        serde_json::from_slice(&output.stdout).expect("valid copy JSON report");
    assert_eq!(report["summary"]["copied"], 1);
    assert_eq!(report["schema_version"], "2.0.0");
    assert_eq!(report["command"], "copy");
    assert_eq!(report["data"]["items"][0]["status"], "copied");
    assert_eq!(
        fs::read_to_string(fixture.right().join("nested/file.txt")).unwrap(),
        "copied"
    );
}

#[test]
fn test_copy_command_keeps_v1_shape_when_requested() {
    let fixture = TestFixture::new();
    fixture.create_left_file("legacy.txt", "legacy copy");

    let output = run_cli_success(&[
        "copy",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--path",
        "legacy.txt",
        "--json",
        "--schema-version",
        "1",
    ]);
    let report: serde_json::Value =
        serde_json::from_slice(&output.stdout).expect("valid legacy copy report");

    assert_eq!(report["schema_version"], "1.0.0");
    assert_eq!(report["items"][0]["status"], "copied");
    assert!(report.get("data").is_none());
}

#[test]
fn test_copy_command_writes_transaction_log() {
    let fixture = TestFixture::new();
    fixture.create_left_file("journaled.txt", "journal me");
    let log_path = fixture.left().parent().unwrap().join("transactions.jsonl");

    let output = run_cli(&[
        "copy",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--path",
        "journaled.txt",
        "--transaction-log",
        log_path.to_str().unwrap(),
    ]);

    assert!(output.status.success(), "copy failed: {:?}", output);
    let log = fs::read_to_string(log_path).unwrap();
    assert!(log.contains("run_started"));
    assert!(log.contains("action_started"));
    assert!(log.contains("action_completed"));
    assert!(log.contains("run_completed"));
}

#[test]
fn test_copy_command_returns_failure_for_missing_source() {
    let fixture = TestFixture::new();
    let output = run_cli(&[
        "copy",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--path",
        "missing.txt",
        "--json",
    ]);

    assert_eq!(output.status.code(), Some(1));
    let report: serde_json::Value =
        serde_json::from_slice(&output.stdout).expect("valid partial copy report");
    assert_eq!(report["summary"]["missing"], 1);
    assert_eq!(report["summary"]["failed"], 0);
    assert_eq!(report["status"], "partial");
    assert_eq!(report["data"]["items"][0]["status"], "missing");
}

#[test]
fn test_sync_command_mutates_and_reports_actions() {
    let fixture = TestFixture::new();
    fixture.create_left_file("sync.txt", "sync me");

    let output = run_cli(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--delete-mode",
        "permanent",
        "--json",
    ]);

    assert!(output.status.success(), "sync failed: {:?}", output);
    let report: serde_json::Value =
        serde_json::from_slice(&output.stdout).expect("valid sync JSON report");
    assert_eq!(report["summary"]["copied"], 1);
    assert_eq!(report["schema_version"], "2.0.0");
    assert_eq!(report["command"], "sync");
    assert_eq!(report["data"]["actions"][0]["code"], "COPY_LR");
    assert_eq!(
        fs::read_to_string(fixture.right().join("sync.txt")).unwrap(),
        "sync me"
    );
}

#[test]
fn sync_checkpoint_can_be_listed_resumed_and_discarded() {
    let fixture = TestFixture::new();
    fixture.create_left_file("sync.txt", "sync me");
    let checkpoint_dir = TempDir::new().expect("checkpoint dir");
    let checkpoint_dir_arg = checkpoint_dir.path().to_str().unwrap();

    let first = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--delete-mode",
        "permanent",
        "--checkpoint-dir",
        checkpoint_dir_arg,
        "--json",
    ]);
    let report: serde_json::Value = serde_json::from_slice(&first.stdout).expect("sync report");
    let id = report["data"]["checkpoint_id"]
        .as_str()
        .unwrap_or_else(|| panic!("missing checkpoint id in report: {report}"));
    let manifest_path = checkpoint_dir.path().join(format!("{id}.json"));
    let mut manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(&manifest_path).unwrap()).expect("checkpoint manifest");
    manifest["status"] = serde_json::Value::String("cancelled".to_string());
    fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();

    let resumed = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--delete-mode",
        "permanent",
        "--checkpoint-dir",
        checkpoint_dir_arg,
        "--resume-checkpoint",
        id,
        "--json",
    ]);
    let resumed_report: serde_json::Value =
        serde_json::from_slice(&resumed.stdout).expect("resumed report");
    assert_eq!(resumed_report["data"]["resumed"], true);
    assert_eq!(resumed_report["data"]["checkpoint_id"], id);
    assert_eq!(resumed_report["summary"]["total_actions"], 0);

    let checkpoints = run_cli_success(&["sync-checkpoints", checkpoint_dir_arg]);
    let listed: serde_json::Value =
        serde_json::from_slice(&checkpoints.stdout).expect("checkpoint list");
    assert_eq!(listed["command"], "sync-checkpoints");
    assert_eq!(listed["summary"]["checkpoint_count"], 1);
    assert_eq!(listed["data"]["checkpoints"].as_array().unwrap().len(), 1);
    assert_eq!(listed["data"]["checkpoints"][0]["id"], id);

    let discarded = run_cli_success(&["sync-discard", checkpoint_dir_arg, id]);
    let discard_report: serde_json::Value =
        serde_json::from_slice(&discarded.stdout).expect("discard report");
    assert_eq!(discard_report["command"], "sync-discard");
    assert_eq!(discard_report["data"]["discarded_id"], id);
    let after_discard = run_cli_success(&["sync-checkpoints", checkpoint_dir_arg]);
    let empty: serde_json::Value =
        serde_json::from_slice(&after_discard.stdout).expect("empty checkpoint list");
    assert_eq!(empty["summary"]["checkpoint_count"], 0);
    assert_eq!(empty["data"]["checkpoints"].as_array().unwrap().len(), 0);
}

#[test]
fn sync_update_and_mirror_modes_handle_target_orphans_differently() {
    let fixture = TestFixture::new();
    fixture.create_left_file("left-only.txt", "left");
    fixture.create_right_file("right-only.txt", "right");

    let update_right = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "update_right",
        "--dry-run",
        "--json",
    ]);
    let update_right_report: serde_json::Value =
        serde_json::from_slice(&update_right.stdout).expect("update-right report");
    assert_eq!(update_right_report["data"]["direction"], "update_right");
    assert_eq!(update_right_report["summary"]["total_actions"], 1);
    assert_eq!(update_right_report["data"]["actions"][0]["code"], "COPY_LR");
    assert_eq!(
        update_right_report["data"]["actions"][0]["path"],
        "left-only.txt"
    );

    let mirror_right = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "mirror_right",
        "--dry-run",
        "--json",
    ]);
    let mirror_right_report: serde_json::Value =
        serde_json::from_slice(&mirror_right.stdout).expect("mirror-right report");
    assert_eq!(mirror_right_report["summary"]["total_actions"], 2);
    assert_eq!(
        mirror_right_report["data"]["actions"][1]["code"],
        "DELETE_R"
    );
    assert_eq!(
        mirror_right_report["data"]["actions"][1]["path"],
        "right-only.txt"
    );

    let update_left = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "update_left",
        "--dry-run",
        "--json",
    ]);
    let update_left_report: serde_json::Value =
        serde_json::from_slice(&update_left.stdout).expect("update-left report");
    assert_eq!(update_left_report["summary"]["total_actions"], 1);
    assert_eq!(update_left_report["data"]["actions"][0]["code"], "COPY_RL");
    assert_eq!(
        update_left_report["data"]["actions"][0]["path"],
        "right-only.txt"
    );

    let mirror_left = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "mirror_left",
        "--dry-run",
        "--json",
    ]);
    let mirror_left_report: serde_json::Value =
        serde_json::from_slice(&mirror_left.stdout).expect("mirror-left report");
    assert_eq!(mirror_left_report["summary"]["total_actions"], 2);
    assert_eq!(mirror_left_report["data"]["actions"][0]["code"], "DELETE_L");
    assert_eq!(mirror_left_report["data"]["actions"][1]["code"], "COPY_RL");

    let update_both = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "update_both",
        "--dry-run",
        "--json",
    ]);
    let update_both_report: serde_json::Value =
        serde_json::from_slice(&update_both.stdout).expect("update-both report");
    assert_eq!(update_both_report["summary"]["total_actions"], 2);
    assert_eq!(update_both_report["data"]["actions"][0]["code"], "COPY_LR");
    assert_eq!(update_both_report["data"]["actions"][1]["code"], "COPY_RL");

    // Preserve the older one-way mode's mirror behavior for existing CLI users.
    let legacy_left_to_right = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "left_to_right",
        "--dry-run",
        "--json",
    ]);
    let legacy_report: serde_json::Value =
        serde_json::from_slice(&legacy_left_to_right.stdout).expect("legacy sync report");
    assert_eq!(legacy_report["summary"]["total_actions"], 2);
    assert_eq!(legacy_report["data"]["actions"][1]["code"], "DELETE_R");

    let update_result = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "update_right",
        "--delete-mode",
        "permanent",
        "--json",
    ]);
    let update_report: serde_json::Value =
        serde_json::from_slice(&update_result.stdout).expect("update execution report");
    assert_eq!(update_report["summary"]["deleted"], 0);
    assert!(fixture.right().join("right-only.txt").exists());
    assert_eq!(
        fs::read_to_string(fixture.right().join("left-only.txt")).unwrap(),
        "left"
    );

    let mirror_result = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--direction",
        "mirror_right",
        "--delete-mode",
        "permanent",
        "--json",
    ]);
    let mirror_report: serde_json::Value =
        serde_json::from_slice(&mirror_result.stdout).expect("mirror execution report");
    assert_eq!(mirror_report["summary"]["deleted"], 1);
    assert!(!fixture.right().join("right-only.txt").exists());
}

#[cfg(unix)]
#[test]
fn sync_sigterm_returns_partial_json_and_journals_cancelled_action() {
    let fixture = TestFixture::new();
    let large_file = fs::File::create(fixture.left().join("large.bin")).expect("large source file");
    large_file
        .set_len(64 * 1024 * 1024)
        .expect("large sparse source");

    let checkpoint_dir = TempDir::new().expect("checkpoint dir");
    let config_dir = TempDir::new().expect("config dir");
    let cache_dir = TempDir::new().expect("cache dir");
    let transaction_log = fixture._temp_dir.path().join("sync.jsonl");
    let mut child = Command::new(env!("CARGO_BIN_EXE_rcompare_cli"))
        .args([
            "sync",
            fixture.left().to_str().unwrap(),
            fixture.right().to_str().unwrap(),
            "--delete-mode",
            "permanent",
            "--checkpoint-dir",
            checkpoint_dir.path().to_str().unwrap(),
            "--transaction-log",
            transaction_log.to_str().unwrap(),
            "--json",
            "--no-cache",
        ])
        .env("XDG_CONFIG_HOME", config_dir.path())
        .env("XDG_CACHE_HOME", cache_dir.path())
        .env("APPDATA", config_dir.path())
        .env("LOCALAPPDATA", cache_dir.path())
        .env("HOME", config_dir.path())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start sync process");

    let deadline = Instant::now() + Duration::from_secs(30);
    loop {
        let journal = fs::read_to_string(&transaction_log).unwrap_or_default();
        if journal.contains("\"event\":\"action_started\"") {
            break;
        }
        if let Some(status) = child.try_wait().expect("poll sync process") {
            panic!("sync exited before starting an action: {status}");
        }
        if Instant::now() >= deadline {
            child.kill().expect("stop timed-out sync process");
            panic!("sync did not reach its first action in 30 seconds");
        }
        thread::sleep(Duration::from_millis(5));
    }

    let signal_result = unsafe { libc::kill(child.id() as i32, libc::SIGTERM) };
    assert_eq!(signal_result, 0, "send SIGTERM to sync process");
    let output = child.wait_with_output().expect("collect sync output");

    assert_eq!(output.status.code(), Some(130));
    let report: serde_json::Value =
        serde_json::from_slice(&output.stdout).expect("cancelled sync JSON report");
    assert_eq!(report["status"], "cancelled");
    assert_eq!(report["summary"]["cancelled"], true);
    assert_eq!(report["summary"]["completed"], 0);
    assert_eq!(report["summary"]["remaining"], 1);
    assert_eq!(report["summary"]["failed"], 0);
    let checkpoint_id = report["data"]["checkpoint_id"]
        .as_str()
        .expect("cancelled sync checkpoint id");
    let manifest_path = checkpoint_dir.path().join(format!("{checkpoint_id}.json"));
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(&manifest_path).expect("read cancelled manifest"))
            .expect("parse cancelled manifest");
    assert_eq!(manifest["status"], "cancelled");

    let resumed = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--delete-mode",
        "permanent",
        "--checkpoint-dir",
        checkpoint_dir.path().to_str().unwrap(),
        "--resume-checkpoint",
        checkpoint_id,
        "--json",
        "--no-cache",
    ]);
    let resumed_report: serde_json::Value =
        serde_json::from_slice(&resumed.stdout).expect("resumed sync JSON report");
    assert_eq!(resumed_report["data"]["resumed"], true);
    assert_eq!(resumed_report["data"]["checkpoint_id"], checkpoint_id);
    assert_eq!(resumed_report["summary"]["copied"], 1);
    assert_eq!(
        fs::metadata(fixture.right().join("large.bin"))
            .expect("resumed destination file")
            .len(),
        64 * 1024 * 1024
    );

    let journal = fs::read_to_string(transaction_log).expect("read transaction log");
    assert!(journal.contains("\"event\":\"action_cancelled\""));
    assert!(journal.contains("\"event\":\"run_cancelled\""));
}

#[test]
fn test_sync_command_keeps_v1_shape_when_requested() {
    let fixture = TestFixture::new();
    fixture.create_left_file("legacy-sync.txt", "legacy sync");

    let output = run_cli_success(&[
        "sync",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--dry-run",
        "--json",
        "--schema-version",
        "1",
    ]);
    let report: serde_json::Value =
        serde_json::from_slice(&output.stdout).expect("valid legacy sync report");

    assert_eq!(report["schema_version"], "1.0.0");
    assert_eq!(report["actions"][0]["code"], "COPY_LR");
    assert!(report.get("data").is_none());
}

#[test]
fn test_scan_overlay_and_glob_filter() {
    let fixture = TestFixture::new();
    let overlay = fixture.left().parent().unwrap().join("overlay");
    fs::create_dir(&overlay).unwrap();
    fs::write(overlay.join("shared.txt"), "shared").unwrap();
    fs::write(overlay.join("ignored.log"), "ignored").unwrap();
    fixture.create_left_file("base.txt", "base");

    let output = run_cli(&[
        "scan",
        fixture.left().to_str().unwrap(),
        fixture.right().to_str().unwrap(),
        "--overlay",
        overlay.to_str().unwrap(),
        "--include",
        "*.txt",
        "--json",
    ]);

    assert!(output.status.success() || output.status.code() == Some(2));
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("base.txt"));
    assert!(stdout.contains("shared.txt"));
    assert!(!stdout.contains("ignored.log"));
}
