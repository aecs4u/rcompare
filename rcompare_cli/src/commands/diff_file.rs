//! `diff-file` command: compute one file-level diff by mode.
use super::support::{
    build_text_diff_config, is_safe_relative_path, is_text_file, read_bytes_from_source_path,
    DiffModeArg, ResolvedDiffMode, WhitespaceModeArg,
};
use rcompare_core::text_diff::DiffChangeType;
use rcompare_core::{
    is_csv_file, is_excel_file, is_image_file, is_json_file, is_parquet_file, is_yaml_file,
    CsvDiffEngine, ExcelDiffEngine, ImageDiffEngine, JsonDiffEngine, ParquetDiffEngine,
    TextDiffEngine,
};
use serde::Serialize;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Serialize)]
pub(crate) struct DiffFileReport {
    pub(crate) schema_version: String,
    pub(crate) left: String,
    pub(crate) right: String,
    pub(crate) path: String,
    pub(crate) mode: String,
    pub(crate) result: serde_json::Value,
}

#[derive(Serialize)]
pub(crate) struct DiffFileTextResult {
    pub(crate) total_lines: usize,
    pub(crate) equal_lines: usize,
    pub(crate) inserted_lines: usize,
    pub(crate) deleted_lines: usize,
    pub(crate) lines: Vec<rcompare_core::text_diff::DiffLine>,
}

#[derive(Serialize)]
pub(crate) struct DiffFileBinaryRange {
    pub(crate) start: u64,
    pub(crate) end_exclusive: u64,
}

#[derive(Serialize)]
pub(crate) struct DiffFileBinaryResult {
    pub(crate) left_size: u64,
    pub(crate) right_size: u64,
    pub(crate) identical: bool,
    pub(crate) mismatch_bytes: u64,
    pub(crate) mismatch_ranges: Vec<DiffFileBinaryRange>,
    pub(crate) truncated_ranges: bool,
}

pub(crate) struct TempFileGuard {
    pub(crate) path: PathBuf,
}

impl TempFileGuard {
    pub(crate) fn create(
        prefix: &str,
        suffix: &str,
        bytes: &[u8],
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let pid = std::process::id();
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let suffix = if suffix.is_empty() {
            "".to_string()
        } else if suffix.starts_with('.') {
            suffix.to_string()
        } else {
            format!(".{suffix}")
        };

        for i in 0..32u32 {
            let path = std::env::temp_dir()
                .join(format!("rcompare_cli_{prefix}_{pid}_{nanos}_{i}{suffix}"));
            if path.exists() {
                continue;
            }
            fs::write(&path, bytes)?;
            return Ok(Self { path });
        }

        Err("failed to allocate temporary file".into())
    }

    pub(crate) fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for TempFileGuard {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

pub(crate) fn run_diff_file(
    left: PathBuf,
    right: PathBuf,
    rel_path: String,
    mode: DiffModeArg,
    json: bool,
    ignore_whitespace: Option<WhitespaceModeArg>,
    ignore_case: bool,
    regex_rules: Vec<String>,
    image_exif: bool,
    image_tolerance: u8,
    max_binary_ranges: usize,
) -> Result<(), Box<dyn std::error::Error>> {
    let rel = PathBuf::from(rel_path.trim());
    if rel.as_os_str().is_empty() {
        return Err("--path cannot be empty".into());
    }
    if !is_safe_relative_path(&rel) {
        return Err("--path must be a safe relative path".into());
    }

    let mode = resolve_diff_mode(&rel, mode);
    let left_bytes = read_bytes_from_source_path(&left, &rel)?;
    let right_bytes = read_bytes_from_source_path(&right, &rel)?;

    let result = match mode {
        ResolvedDiffMode::Text => {
            let config = build_text_diff_config(ignore_whitespace, ignore_case, regex_rules)?;
            let engine = TextDiffEngine::with_config(config);
            let left_text = String::from_utf8(left_bytes)
                .map_err(|_| "left file is not valid UTF-8; use --mode binary")?;
            let right_text = String::from_utf8(right_bytes)
                .map_err(|_| "right file is not valid UTF-8; use --mode binary")?;
            let lines = engine.compare_text_patience(&left_text, &right_text, &rel)?;
            let mut equal_lines = 0usize;
            let mut inserted_lines = 0usize;
            let mut deleted_lines = 0usize;
            for line in &lines {
                match line.change_type {
                    DiffChangeType::Equal => equal_lines += 1,
                    DiffChangeType::Insert => inserted_lines += 1,
                    DiffChangeType::Delete => deleted_lines += 1,
                }
            }
            serde_json::to_value(DiffFileTextResult {
                total_lines: lines.len(),
                equal_lines,
                inserted_lines,
                deleted_lines,
                lines,
            })?
        }
        ResolvedDiffMode::Binary => serde_json::to_value(build_binary_diff_result(
            &left_bytes,
            &right_bytes,
            max_binary_ranges,
        ))?,
        ResolvedDiffMode::Image => {
            let suffix = rel
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("img")
                .to_string();
            let left_tmp = TempFileGuard::create("diff_img_left", &suffix, &left_bytes)?;
            let right_tmp = TempFileGuard::create("diff_img_right", &suffix, &right_bytes)?;
            let engine = ImageDiffEngine::new()
                .with_exif_compare(image_exif)
                .with_tolerance(image_tolerance);
            let result = engine.compare_files(left_tmp.path(), right_tmp.path())?;
            serde_json::to_value(result)?
        }
        ResolvedDiffMode::Csv => {
            let left_tmp = TempFileGuard::create("diff_csv_left", "csv", &left_bytes)?;
            let right_tmp = TempFileGuard::create("diff_csv_right", "csv", &right_bytes)?;
            let engine = CsvDiffEngine::new();
            let result = engine.compare_files(left_tmp.path(), right_tmp.path())?;
            serde_json::to_value(result)?
        }
        ResolvedDiffMode::Excel => {
            let suffix = rel
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("xlsx")
                .to_string();
            let left_tmp = TempFileGuard::create("diff_excel_left", &suffix, &left_bytes)?;
            let right_tmp = TempFileGuard::create("diff_excel_right", &suffix, &right_bytes)?;
            let engine = ExcelDiffEngine::new();
            let result = engine.compare_files(left_tmp.path(), right_tmp.path())?;
            serde_json::to_value(result)?
        }
        ResolvedDiffMode::Json => {
            let left_tmp = TempFileGuard::create("diff_json_left", "json", &left_bytes)?;
            let right_tmp = TempFileGuard::create("diff_json_right", "json", &right_bytes)?;
            let engine = JsonDiffEngine::new();
            let result = engine.compare_json_files(left_tmp.path(), right_tmp.path())?;
            serde_json::to_value(result)?
        }
        ResolvedDiffMode::Yaml => {
            let suffix = rel
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("yaml")
                .to_string();
            let left_tmp = TempFileGuard::create("diff_yaml_left", &suffix, &left_bytes)?;
            let right_tmp = TempFileGuard::create("diff_yaml_right", &suffix, &right_bytes)?;
            let engine = JsonDiffEngine::new();
            let result = engine.compare_yaml_files(left_tmp.path(), right_tmp.path())?;
            serde_json::to_value(result)?
        }
        ResolvedDiffMode::Parquet => {
            let left_tmp = TempFileGuard::create("diff_parquet_left", "parquet", &left_bytes)?;
            let right_tmp = TempFileGuard::create("diff_parquet_right", "parquet", &right_bytes)?;
            let engine = ParquetDiffEngine::new();
            let result = engine.compare_parquet_files(left_tmp.path(), right_tmp.path())?;
            serde_json::to_value(result)?
        }
    };

    let report = DiffFileReport {
        schema_version: "1.0.0".to_string(),
        left: left.to_string_lossy().to_string(),
        right: right.to_string_lossy().to_string(),
        path: rel.to_string_lossy().to_string(),
        mode: mode.as_str().to_string(),
        result,
    };

    if json {
        println!("{}", serde_json::to_string_pretty(&report)?);
    } else {
        println!("Diff file");
        println!("Left : {}", report.left);
        println!("Right: {}", report.right);
        println!("Path : {}", report.path);
        println!("Mode : {}", report.mode);
        println!("{}", serde_json::to_string_pretty(&report.result)?);
    }

    Ok(())
}

/// Resolve a requested mode to a concrete comparison mode. `Auto` sniffs the
/// file extension; every other variant already IS the answer, since clap
/// only ever hands us one of the `DiffModeArg` values in the first place.
pub(crate) fn resolve_diff_mode(path: &Path, requested_mode: DiffModeArg) -> ResolvedDiffMode {
    match requested_mode {
        DiffModeArg::Auto => {
            if is_image_file(path) {
                ResolvedDiffMode::Image
            } else if is_csv_file(path) {
                ResolvedDiffMode::Csv
            } else if is_excel_file(path) {
                ResolvedDiffMode::Excel
            } else if is_json_file(path) {
                ResolvedDiffMode::Json
            } else if is_yaml_file(path) {
                ResolvedDiffMode::Yaml
            } else if is_parquet_file(path) {
                ResolvedDiffMode::Parquet
            } else if is_text_file(path) {
                ResolvedDiffMode::Text
            } else {
                ResolvedDiffMode::Binary
            }
        }
        DiffModeArg::Text => ResolvedDiffMode::Text,
        DiffModeArg::Binary => ResolvedDiffMode::Binary,
        DiffModeArg::Image => ResolvedDiffMode::Image,
        DiffModeArg::Csv => ResolvedDiffMode::Csv,
        DiffModeArg::Excel => ResolvedDiffMode::Excel,
        DiffModeArg::Json => ResolvedDiffMode::Json,
        DiffModeArg::Yaml => ResolvedDiffMode::Yaml,
        DiffModeArg::Parquet => ResolvedDiffMode::Parquet,
    }
}

pub(crate) fn build_binary_diff_result(
    left: &[u8],
    right: &[u8],
    max_ranges: usize,
) -> DiffFileBinaryResult {
    let left_size = left.len() as u64;
    let right_size = right.len() as u64;
    let max_len = left.len().max(right.len());

    let mut mismatch_bytes = 0u64;
    let mut ranges = Vec::new();
    let mut range_start: Option<usize> = None;

    for i in 0..max_len {
        let l = left.get(i).copied();
        let r = right.get(i).copied();
        let is_diff = match (l, r) {
            (Some(a), Some(b)) => a != b,
            _ => true,
        };

        if is_diff {
            mismatch_bytes += 1;
            if range_start.is_none() {
                range_start = Some(i);
            }
        } else if let Some(start) = range_start.take() {
            ranges.push(DiffFileBinaryRange {
                start: start as u64,
                end_exclusive: i as u64,
            });
        }
    }

    if let Some(start) = range_start.take() {
        ranges.push(DiffFileBinaryRange {
            start: start as u64,
            end_exclusive: max_len as u64,
        });
    }

    let truncated_ranges = if max_ranges == 0 {
        !ranges.is_empty()
    } else {
        ranges.len() > max_ranges
    };
    if max_ranges == 0 {
        ranges.clear();
    } else if ranges.len() > max_ranges {
        ranges.truncate(max_ranges);
    }

    DiffFileBinaryResult {
        left_size,
        right_size,
        identical: mismatch_bytes == 0,
        mismatch_bytes,
        mismatch_ranges: ranges,
        truncated_ranges,
    }
}
