use filetime::{set_file_mtime, FileTime};
use rcompare_common::Vfs;
use rcompare_core::vfs::{Writable7zVfs, WritableTarVfs, WritableZipVfs};
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::process::Command;
use tempfile::TempDir;

fn run_cli_json(args: &[&str]) -> Value {
    let exe = env!("CARGO_BIN_EXE_rcompare_cli");
    let config_dir = TempDir::new().expect("config dir");
    let cache_dir = TempDir::new().expect("cache dir");
    let output = Command::new(exe)
        .args(args)
        .env("XDG_CONFIG_HOME", config_dir.path())
        .env("XDG_CACHE_HOME", cache_dir.path())
        .env("APPDATA", config_dir.path())
        .env("LOCALAPPDATA", cache_dir.path())
        .env("HOME", config_dir.path())
        .output()
        .expect("failed to run rcompare_cli");

    let code = output.status.code().unwrap_or(-1);
    assert!(
        code == 0 || code == 2,
        "command failed: {} (expected 0 or 2)\n{}",
        output.status,
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("stdout not utf-8");
    serde_json::from_str(&stdout).expect("invalid json output")
}

fn write_archive_files(vfs: &dyn Vfs, files: &[(&str, &str)]) {
    for (path, contents) in files {
        vfs.write_file(Path::new(path), contents.as_bytes())
            .expect("write archive file");
    }
    vfs.flush().expect("flush archive");
}

fn create_zip_archive(path: &Path, files: &[(&str, &str)]) {
    let vfs = WritableZipVfs::create(path.to_path_buf()).expect("create zip archive");
    write_archive_files(&vfs, files);
}

fn create_tar_gz_archive(path: &Path, files: &[(&str, &str)]) {
    let vfs = WritableTarVfs::create(path.to_path_buf()).expect("create tar.gz archive");
    write_archive_files(&vfs, files);
}

fn create_7z_archive(path: &Path, files: &[(&str, &str)]) {
    let vfs = Writable7zVfs::create(path.to_path_buf()).expect("create 7z archive");
    write_archive_files(&vfs, files);
}

fn entries_by_path(report: &Value) -> HashMap<String, String> {
    let mut map = HashMap::new();
    let entries = report["entries"].as_array().expect("entries array missing");
    for entry in entries {
        let path = entry["path"].as_str().unwrap_or("").to_string();
        let status = entry["status"].as_str().unwrap_or("").to_string();
        map.insert(path, status);
    }
    map
}

fn assert_side_schema(side: &Value) {
    let obj = side.as_object().expect("side should be object");
    assert!(obj.get("size").and_then(Value::as_u64).is_some());
    assert!(obj.get("is_dir").and_then(Value::as_bool).is_some());

    let modified = obj.get("modified_unix").expect("modified_unix missing");
    assert!(modified.is_null() || modified.as_u64().is_some());
}

fn assert_entry_schema(entry: &Value) {
    let path = entry
        .get("path")
        .and_then(Value::as_str)
        .expect("path string");
    let status = entry
        .get("status")
        .and_then(Value::as_str)
        .expect("status string");
    let left = entry.get("left").unwrap_or(&Value::Null);
    let right = entry.get("right").unwrap_or(&Value::Null);

    let left_is_obj = left.is_object();
    let right_is_obj = right.is_object();
    assert!(left_is_obj || right_is_obj);

    if path.is_empty() {
        if left_is_obj {
            assert_side_schema(left);
            assert_eq!(left.get("is_dir").and_then(Value::as_bool), Some(true));
        }
        if right_is_obj {
            assert_side_schema(right);
            assert_eq!(right.get("is_dir").and_then(Value::as_bool), Some(true));
        }
        return;
    }

    if left_is_obj {
        assert_side_schema(left);
    }
    if right_is_obj {
        assert_side_schema(right);
    }

    match status {
        "OrphanLeft" => {
            assert!(left_is_obj);
            assert!(!right_is_obj);
        }
        "OrphanRight" => {
            assert!(right_is_obj);
            assert!(!left_is_obj);
        }
        "Same" | "Different" | "Unchecked" => {}
        other => panic!("unexpected status: {other}"),
    }
}

#[test]
fn scan_json_basic_statuses() {
    let left = TempDir::new().expect("left dir");
    let right = TempDir::new().expect("right dir");

    let same_left = left.path().join("same.txt");
    let same_right = right.path().join("same.txt");
    fs::write(&same_left, "same").unwrap();
    fs::write(&same_right, "same").unwrap();

    // Set matching timestamps to ensure files are marked as "Same"
    let mtime = FileTime::from_unix_time(1_700_000_000, 0);
    set_file_mtime(&same_left, mtime).unwrap();
    set_file_mtime(&same_right, mtime).unwrap();

    fs::write(left.path().join("diff.txt"), "abc").unwrap();
    fs::write(right.path().join("diff.txt"), "abcd").unwrap();

    fs::write(left.path().join("left_only.txt"), "left").unwrap();
    fs::write(right.path().join("right_only.txt"), "right").unwrap();

    let report = run_cli_json(&[
        "scan",
        left.path().to_str().unwrap(),
        right.path().to_str().unwrap(),
        "--json",
    ]);

    let map = entries_by_path(&report);
    assert_eq!(map.get("same.txt").map(String::as_str), Some("Same"));
    assert_eq!(map.get("diff.txt").map(String::as_str), Some("Different"));
    assert_eq!(
        map.get("left_only.txt").map(String::as_str),
        Some("OrphanLeft")
    );
    assert_eq!(
        map.get("right_only.txt").map(String::as_str),
        Some("OrphanRight")
    );
}

#[test]
fn scan_json_diff_only_filters_same() {
    let left = TempDir::new().expect("left dir");
    let right = TempDir::new().expect("right dir");

    let same_left = left.path().join("same.txt");
    let same_right = right.path().join("same.txt");
    fs::write(&same_left, "same").unwrap();
    fs::write(&same_right, "same").unwrap();

    // Set matching timestamps to ensure files are marked as "Same"
    let mtime = FileTime::from_unix_time(1_700_000_000, 0);
    set_file_mtime(&same_left, mtime).unwrap();
    set_file_mtime(&same_right, mtime).unwrap();

    fs::write(left.path().join("left_only.txt"), "left").unwrap();

    let report = run_cli_json(&[
        "scan",
        left.path().to_str().unwrap(),
        right.path().to_str().unwrap(),
        "--diff-only",
        "--json",
    ]);

    let map = entries_by_path(&report);
    assert!(!map.contains_key("same.txt"));
    assert_eq!(
        map.get("left_only.txt").map(String::as_str),
        Some("OrphanLeft")
    );
}

#[test]
fn scan_json_verify_hashes_detects_same_size_changes() {
    let left = TempDir::new().expect("left dir");
    let right = TempDir::new().expect("right dir");

    let left_path = left.path().join("hash.txt");
    let right_path = right.path().join("hash.txt");

    fs::write(&left_path, "abcd").unwrap();
    fs::write(&right_path, "abce").unwrap();

    let mtime = FileTime::from_unix_time(1_700_000_000, 0);
    set_file_mtime(&left_path, mtime).unwrap();
    set_file_mtime(&right_path, mtime).unwrap();

    let report_no_verify = run_cli_json(&[
        "scan",
        left.path().to_str().unwrap(),
        right.path().to_str().unwrap(),
        "--no-verify-hashes",
        "--json",
    ]);
    let map_no_verify = entries_by_path(&report_no_verify);
    assert_eq!(
        map_no_verify.get("hash.txt").map(String::as_str),
        Some("Same")
    );

    let report_verify = run_cli_json(&[
        "scan",
        left.path().to_str().unwrap(),
        right.path().to_str().unwrap(),
        "--verify-hashes",
        "--json",
    ]);
    let map_verify = entries_by_path(&report_verify);
    assert_eq!(
        map_verify.get("hash.txt").map(String::as_str),
        Some("Different")
    );
}

#[test]
fn scan_json_zip_archives() {
    let temp = TempDir::new().expect("temp dir");
    let left_zip = temp.path().join("left.zip");
    let right_zip = temp.path().join("right.zip");

    create_zip_archive(
        &left_zip,
        &[
            ("same.txt", "same"),
            ("diff.txt", "left side"),
            ("left_only.txt", "left only"),
        ],
    );
    create_zip_archive(
        &right_zip,
        &[
            ("same.txt", "same"),
            ("diff.txt", "right side"),
            ("right_only.txt", "right only"),
        ],
    );

    let report = run_cli_json(&[
        "scan",
        left_zip.to_str().unwrap(),
        right_zip.to_str().unwrap(),
        "--json",
    ]);

    let map = entries_by_path(&report);
    assert_eq!(map.get("same.txt").map(String::as_str), Some("Same"));
    assert_eq!(map.get("diff.txt").map(String::as_str), Some("Different"));
    assert_eq!(
        map.get("left_only.txt").map(String::as_str),
        Some("OrphanLeft")
    );
    assert_eq!(
        map.get("right_only.txt").map(String::as_str),
        Some("OrphanRight")
    );
}

#[test]
fn scan_json_tar_gz_archive_vs_directory() {
    let temp = TempDir::new().expect("temp dir");
    let left_tar = temp.path().join("left.tar.gz");
    create_tar_gz_archive(
        &left_tar,
        &[
            ("same.txt", "same"),
            ("diff.txt", "left side"),
            ("left_only.txt", "left only"),
        ],
    );

    let right = TempDir::new().expect("right dir");
    fs::write(right.path().join("same.txt"), "same").unwrap();
    fs::write(right.path().join("diff.txt"), "right side").unwrap();
    fs::write(right.path().join("right_only.txt"), "right only").unwrap();

    let report = run_cli_json(&[
        "scan",
        left_tar.to_str().unwrap(),
        right.path().to_str().unwrap(),
        "--json",
    ]);

    let map = entries_by_path(&report);
    assert_eq!(map.get("same.txt").map(String::as_str), Some("Same"));
    assert_eq!(map.get("diff.txt").map(String::as_str), Some("Different"));
    assert_eq!(
        map.get("left_only.txt").map(String::as_str),
        Some("OrphanLeft")
    );
    assert_eq!(
        map.get("right_only.txt").map(String::as_str),
        Some("OrphanRight")
    );
}

#[test]
fn scan_json_7z_archives() {
    let temp = TempDir::new().expect("temp dir");
    let left_7z = temp.path().join("left.7z");
    let right_7z = temp.path().join("right.7z");

    create_7z_archive(
        &left_7z,
        &[
            ("same.txt", "same"),
            ("diff.txt", "left side"),
            ("left_only.txt", "left only"),
        ],
    );
    create_7z_archive(
        &right_7z,
        &[
            ("same.txt", "same"),
            ("diff.txt", "right side"),
            ("right_only.txt", "right only"),
        ],
    );

    let report = run_cli_json(&[
        "scan",
        left_7z.to_str().unwrap(),
        right_7z.to_str().unwrap(),
        "--json",
    ]);

    let map = entries_by_path(&report);
    assert_eq!(map.get("same.txt").map(String::as_str), Some("Same"));
    assert_eq!(map.get("diff.txt").map(String::as_str), Some("Different"));
    assert_eq!(
        map.get("left_only.txt").map(String::as_str),
        Some("OrphanLeft")
    );
    assert_eq!(
        map.get("right_only.txt").map(String::as_str),
        Some("OrphanRight")
    );
}

#[test]
fn scan_json_entry_schema_and_unchecked_status() {
    let left = TempDir::new().expect("left dir");
    let right = TempDir::new().expect("right dir");

    let same_left = left.path().join("same.txt");
    let same_right = right.path().join("same.txt");
    fs::write(&same_left, "same").unwrap();
    fs::write(&same_right, "same").unwrap();

    let diff_left = left.path().join("diff.txt");
    let diff_right = right.path().join("diff.txt");
    fs::write(&diff_left, "left").unwrap();
    fs::write(&diff_right, "right").unwrap();

    let unchecked_left = left.path().join("unchecked.txt");
    let unchecked_right = right.path().join("unchecked.txt");
    fs::write(&unchecked_left, "aaaa").unwrap();
    fs::write(&unchecked_right, "bbbb").unwrap();

    let same_mtime = FileTime::from_unix_time(1_700_000_000, 0);
    let left_mtime = FileTime::from_unix_time(1_700_000_100, 0);
    let right_mtime = FileTime::from_unix_time(1_700_000_200, 0);

    set_file_mtime(&same_left, same_mtime).unwrap();
    set_file_mtime(&same_right, same_mtime).unwrap();
    set_file_mtime(&unchecked_left, left_mtime).unwrap();
    set_file_mtime(&unchecked_right, right_mtime).unwrap();

    fs::write(left.path().join("left_only.txt"), "left only").unwrap();
    fs::write(right.path().join("right_only.txt"), "right only").unwrap();

    let report = run_cli_json(&[
        "scan",
        left.path().to_str().unwrap(),
        right.path().to_str().unwrap(),
        "--no-verify-hashes",
        "--json",
    ]);

    let entries = report["entries"].as_array().expect("entries array missing");
    for entry in entries {
        assert_entry_schema(entry);
    }

    let map = entries_by_path(&report);
    assert_eq!(map.get("same.txt").map(String::as_str), Some("Same"));
    assert_eq!(map.get("diff.txt").map(String::as_str), Some("Different"));
    assert_eq!(
        map.get("unchecked.txt").map(String::as_str),
        Some("Unchecked")
    );
    assert_eq!(
        map.get("left_only.txt").map(String::as_str),
        Some("OrphanLeft")
    );
    assert_eq!(
        map.get("right_only.txt").map(String::as_str),
        Some("OrphanRight")
    );
}
