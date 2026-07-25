//! `copy` command: copy selected relative paths between left and right roots.
use super::support::{apply_copy, is_safe_relative_path};
use serde::Serialize;
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Serialize, Clone)]
pub(crate) struct CopyItemReport {
    pub(crate) path: String,
    pub(crate) status: String,
    pub(crate) detail: String,
}


#[derive(Default, Serialize)]
pub(crate) struct CopySummaryReport {
    pub(crate) total_paths: usize,
    pub(crate) copied: usize,
    pub(crate) missing: usize,
    pub(crate) skipped: usize,
    pub(crate) failed: usize,
}


#[derive(Serialize)]
pub(crate) struct CopyReport {
    pub(crate) schema_version: String,
    pub(crate) left: String,
    pub(crate) right: String,
    pub(crate) direction: String,
    pub(crate) dry_run: bool,
    pub(crate) summary: CopySummaryReport,
    pub(crate) items: Vec<CopyItemReport>,
}


pub(crate) fn run_copy(
    left: PathBuf,
    right: PathBuf,
    direction: String,
    paths: Vec<String>,
    paths_file: Option<PathBuf>,
    dry_run: bool,
    json: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    if !left.is_dir() || !right.is_dir() {
        return Err("copy currently supports local directory paths only".into());
    }

    let direction = direction.to_lowercase();
    if !matches!(direction.as_str(), "left_to_right" | "right_to_left") {
        return Err("invalid --direction. Use: left_to_right, right_to_left".into());
    }

    let selected_paths = collect_copy_paths(&paths, paths_file.as_deref())?;
    if selected_paths.is_empty() {
        return Err("no paths selected. Use --path or --paths-file".into());
    }

    let mut summary = CopySummaryReport {
        total_paths: selected_paths.len(),
        ..CopySummaryReport::default()
    };
    let mut items = Vec::with_capacity(selected_paths.len());

    for rel_path in selected_paths {
        let rel = Path::new(&rel_path);
        if !is_safe_relative_path(rel) {
            summary.skipped += 1;
            items.push(CopyItemReport {
                path: rel_path,
                status: "skipped".to_string(),
                detail: "Invalid relative path (must not be absolute or contain '..')".to_string(),
            });
            continue;
        }

        let source = if direction == "left_to_right" {
            left.join(rel)
        } else {
            right.join(rel)
        };
        let target = if direction == "left_to_right" {
            right.join(rel)
        } else {
            left.join(rel)
        };

        if !source.exists() {
            summary.missing += 1;
            items.push(CopyItemReport {
                path: rel_path,
                status: "missing".to_string(),
                detail: "Source path does not exist".to_string(),
            });
            continue;
        }

        if dry_run {
            summary.copied += 1;
            items.push(CopyItemReport {
                path: rel_path,
                status: "planned".to_string(),
                detail: format!(
                    "Would copy {} -> {}",
                    source.display(),
                    target.display()
                ),
            });
            continue;
        }

        match apply_copy(&source, &target) {
            Ok(()) => {
                summary.copied += 1;
                items.push(CopyItemReport {
                    path: rel_path,
                    status: "copied".to_string(),
                    detail: "Copied successfully".to_string(),
                });
            }
            Err(e) => {
                summary.failed += 1;
                items.push(CopyItemReport {
                    path: rel_path,
                    status: "failed".to_string(),
                    detail: e.to_string(),
                });
            }
        }
    }

    let report = CopyReport {
        schema_version: "1.0.0".to_string(),
        left: left.to_string_lossy().to_string(),
        right: right.to_string_lossy().to_string(),
        direction,
        dry_run,
        summary,
        items,
    };

    if json {
        println!("{}", serde_json::to_string_pretty(&report)?);
    } else {
        println!("Copy {}", if dry_run { "(dry-run)" } else { "" });
        println!("Left : {}", report.left);
        println!("Right: {}", report.right);
        println!("Mode : {}", report.direction);
        println!(
            "Summary: {} copied/planned, {} missing, {} skipped, {} failed",
            report.summary.copied,
            report.summary.missing,
            report.summary.skipped,
            report.summary.failed
        );
    }

    Ok(())
}


pub(crate) fn collect_copy_paths(
    cli_paths: &[String],
    paths_file: Option<&Path>,
) -> Result<Vec<String>, Box<dyn std::error::Error>> {
    let mut set = BTreeSet::new();

    for p in cli_paths {
        let trimmed = p.trim();
        if !trimmed.is_empty() {
            set.insert(trimmed.to_string());
        }
    }

    if let Some(file_path) = paths_file {
        let data = fs::read_to_string(file_path)?;
        for line in data.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            set.insert(trimmed.to_string());
        }
    }

    Ok(set.into_iter().collect())
}
