#![allow(clippy::unwrap_used)]

use std::fs;
use std::process::{Command, Output};
use tempfile::TempDir;

fn run_cli(args: &[&str]) -> Output {
    let config_dir = TempDir::new().expect("config dir");
    let cache_dir = TempDir::new().expect("cache dir");
    Command::new(env!("CARGO_BIN_EXE_rcompare_cli"))
        .args(args)
        .env("XDG_CONFIG_HOME", config_dir.path())
        .env("XDG_CACHE_HOME", cache_dir.path())
        .env("APPDATA", config_dir.path())
        .env("LOCALAPPDATA", cache_dir.path())
        .env("HOME", config_dir.path())
        .output()
        .expect("run rcompare_cli")
}

#[test]
fn read_out_streams_binary_file_and_reports_byte_count() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("left");
    let right = temp.path().join("right");
    let source = left.join("nested/file.bin");
    let output_path = temp.path().join("staged/file.bin");
    let bytes = [0, 1, 2, 0xff, 0x80, b't', b'a', b'i', b'l'];
    fs::create_dir_all(source.parent().unwrap()).unwrap();
    fs::create_dir_all(&right).unwrap();
    fs::write(&source, bytes).unwrap();

    let output = run_cli(&[
        "read",
        left.to_str().unwrap(),
        right.to_str().unwrap(),
        "--side",
        "left",
        "--path",
        "nested/file.bin",
        "--out",
        output_path.to_str().unwrap(),
    ]);

    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(fs::read(&output_path).unwrap(), bytes);
    assert!(String::from_utf8_lossy(&output.stdout).contains("Wrote 9 bytes"));
}

#[test]
fn read_writes_exact_binary_payload_to_stdout() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("left");
    let right = temp.path().join("right");
    let bytes = [0, 0xff, 0x80, 0x01, b'\n'];
    fs::create_dir_all(&left).unwrap();
    fs::create_dir_all(&right).unwrap();
    fs::write(left.join("file.bin"), bytes).unwrap();

    let output = run_cli(&[
        "read",
        left.to_str().unwrap(),
        right.to_str().unwrap(),
        "--side",
        "left",
        "--path",
        "file.bin",
    ]);

    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(output.stdout, bytes);
}

#[test]
fn read_missing_file_removes_partial_output() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("left");
    let right = temp.path().join("right");
    let output_path = temp.path().join("staged/missing.bin");
    fs::create_dir_all(&left).unwrap();
    fs::create_dir_all(&right).unwrap();

    let output = run_cli(&[
        "read",
        left.to_str().unwrap(),
        right.to_str().unwrap(),
        "--side",
        "left",
        "--path",
        "missing.bin",
        "--out",
        output_path.to_str().unwrap(),
    ]);

    assert_eq!(output.status.code(), Some(1));
    assert!(!output_path.exists());
}

#[test]
fn read_failure_preserves_existing_output() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("left");
    let right = temp.path().join("right");
    let output_path = temp.path().join("existing.bin");
    fs::create_dir_all(&left).unwrap();
    fs::create_dir_all(&right).unwrap();
    fs::write(&output_path, b"keep previous output").unwrap();

    let output = run_cli(&[
        "read",
        left.to_str().unwrap(),
        right.to_str().unwrap(),
        "--side",
        "left",
        "--path",
        "missing.bin",
        "--out",
        output_path.to_str().unwrap(),
    ]);

    assert_eq!(output.status.code(), Some(1));
    assert_eq!(fs::read(output_path).unwrap(), b"keep previous output");
}
