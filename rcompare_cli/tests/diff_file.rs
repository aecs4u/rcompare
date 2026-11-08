#![allow(clippy::unwrap_used)]
// Integration fixtures intentionally use small local files.

use serde_json::Value;
use std::fs;
#[cfg(feature = "cloud")]
use std::io::{Read, Write};
#[cfg(feature = "cloud")]
use std::net::TcpListener;
use std::process::{Command, Output};
#[cfg(feature = "cloud")]
use std::thread;
#[cfg(feature = "cloud")]
use std::time::{Duration, Instant};
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
        .env("NO_PROXY", "127.0.0.1,localhost")
        .env("no_proxy", "127.0.0.1,localhost")
        .output()
        .expect("run rcompare_cli")
}

fn json_report(output: &Output) -> Value {
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("valid diff-file JSON")
}

#[test]
fn diff_file_accepts_two_explicit_files_with_different_names() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("before.txt");
    let right = temp.path().join("after.md");
    fs::write(&left, "unchanged\nleft value\n").unwrap();
    fs::write(&right, "unchanged\nright value\n").unwrap();

    let output = run_cli(&[
        "diff-file",
        left.to_str().unwrap(),
        right.to_str().unwrap(),
        "--json",
    ]);
    let report = json_report(&output);

    assert_eq!(report["schema_version"], "2.0.0");
    assert_eq!(report["command"], "diff-file");
    assert_eq!(report["summary"]["path"], "before.txt ↔ after.md");
    assert_eq!(report["data"]["left"], left.to_string_lossy().as_ref());
    assert_eq!(report["data"]["right"], right.to_string_lossy().as_ref());
    assert_eq!(report["data"]["path"], "before.txt ↔ after.md");
    assert_eq!(report["data"]["mode"], "text");
    assert!(report["data"]["result"]["inserted_lines"].as_u64().unwrap() > 0);
    assert!(report["data"]["result"]["deleted_lines"].as_u64().unwrap() > 0);
}

#[test]
fn diff_file_keeps_v1_shape_when_requested() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("old.txt");
    let right = temp.path().join("new.txt");
    fs::write(&left, "old\n").unwrap();
    fs::write(&right, "new\n").unwrap();

    let output = run_cli(&[
        "diff-file",
        left.to_str().unwrap(),
        right.to_str().unwrap(),
        "--json",
        "--schema-version",
        "1",
    ]);
    let report = json_report(&output);

    assert_eq!(report["schema_version"], "1.0.0");
    assert_eq!(report["left"], left.to_string_lossy().as_ref());
    assert!(report.get("data").is_none());
}

#[test]
fn diff_file_keeps_shared_relative_path_mode_for_source_roots() {
    let temp = TempDir::new().expect("temporary directory");
    let left_root = temp.path().join("left");
    let right_root = temp.path().join("right");
    fs::create_dir_all(left_root.join("nested")).unwrap();
    fs::create_dir_all(right_root.join("nested")).unwrap();
    fs::write(left_root.join("nested/file.txt"), "left\n").unwrap();
    fs::write(right_root.join("nested/file.txt"), "right\n").unwrap();

    let output = run_cli(&[
        "diff-file",
        left_root.to_str().unwrap(),
        right_root.to_str().unwrap(),
        "--path",
        "nested/file.txt",
        "--json",
    ]);
    let report = json_report(&output);
    assert_eq!(report["data"]["path"], "nested/file.txt");
    assert_eq!(report["data"]["mode"], "text");
}

#[test]
fn diff_file_requires_path_when_operands_are_source_roots() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("left");
    let right = temp.path().join("right");
    fs::create_dir(&left).unwrap();
    fs::create_dir(&right).unwrap();

    let output = run_cli(&["diff-file", left.to_str().unwrap(), right.to_str().unwrap()]);
    assert_eq!(output.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&output.stderr).contains("pass two existing files without --path")
    );
}

#[test]
fn diff_file_direct_mode_rejects_non_files() {
    let temp = TempDir::new().expect("temporary directory");
    let left = temp.path().join("left.txt");
    let right = temp.path().join("right.txt");
    fs::write(&left, "left\n").unwrap();

    let output = run_cli(&[
        "diff-file",
        left.to_str().unwrap(),
        right.to_str().unwrap(),
        "--json",
    ]);
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("two existing files"));
}

#[cfg(not(feature = "cloud"))]
#[test]
fn diff_file_explains_when_remote_sources_are_not_built_in() {
    let output = run_cli(&[
        "diff-file",
        "s3://left-bucket/archive/before.txt",
        "s3://right-bucket/archive/after.txt",
        "--json",
    ]);

    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("rebuild with the `cloud` feature"));
}

#[cfg(feature = "cloud")]
#[test]
fn diff_file_reads_different_files_from_a_local_webdav_endpoint() {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind local WebDAV fixture");
    listener
        .set_nonblocking(true)
        .expect("set nonblocking listener");
    let address = listener.local_addr().expect("fixture address");
    let server = thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut requests_served = 0;
        while requests_served < 4 {
            let (mut stream, _) = match listener.accept() {
                Ok(connection) => connection,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    if Instant::now() >= deadline {
                        break;
                    }
                    thread::sleep(Duration::from_millis(10));
                    continue;
                }
                Err(error) => panic!("accept WebDAV request: {error}"),
            };
            let mut request = Vec::new();
            let mut chunk = [0_u8; 1024];
            loop {
                let read = stream.read(&mut chunk).expect("read WebDAV request");
                if read == 0 {
                    break;
                }
                request.extend_from_slice(&chunk[..read]);
                if request.windows(4).any(|part| part == b"\r\n\r\n") {
                    break;
                }
            }

            let request_text = String::from_utf8_lossy(&request);
            let mut parts = request_text
                .lines()
                .next()
                .unwrap_or_default()
                .split_whitespace();
            let method = parts.next().unwrap_or_default();
            let path = parts.next().unwrap_or_default();
            let (status, content_type, body) = if method == "PROPFIND" {
                let body = format!(
                    "<?xml version=\"1.0\"?><d:multistatus xmlns:d=\"DAV:\"><d:response><d:href>{path}</d:href><d:propstat><d:prop><d:getcontentlength>4</d:getcontentlength><d:resourcetype/></d:prop></d:propstat></d:response></d:multistatus>"
                );
                ("207 Multi-Status", "application/xml", body.into_bytes())
            } else {
                let body = match path {
                    "/left/before.txt" => b"old\n".as_slice(),
                    "/right/after.md" => b"new\n".as_slice(),
                    _ => panic!("unexpected WebDAV GET path: {path}"),
                };
                ("200 OK", "application/octet-stream", body.to_vec())
            };

            write!(
                stream,
                "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            )
            .expect("write WebDAV response headers");
            stream.write_all(&body).expect("write WebDAV response body");
            requests_served += 1;
        }
        requests_served
    });

    let left = format!("dav://{address}/left/before.txt");
    let right = format!("dav://{address}/right/after.md");
    let output = run_cli(&["diff-file", &left, &right, "--json"]);
    let requests_served = server.join().expect("WebDAV fixture server");
    assert_eq!(
        requests_served,
        4,
        "expected metadata and file reads per side; CLI status {:?}; stderr: {}",
        output.status.code(),
        String::from_utf8_lossy(&output.stderr)
    );
    let report = json_report(&output);

    assert_eq!(report["data"]["path"], "before.txt ↔ after.md");
    assert_eq!(report["data"]["mode"], "text");
    assert!(report["data"]["result"]["inserted_lines"].as_u64().unwrap() > 0);
    assert!(report["data"]["result"]["deleted_lines"].as_u64().unwrap() > 0);
}
