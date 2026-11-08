//! `copy` command: copy selected relative paths between left and right roots.
use super::support::{
    build_mutation_endpoint, copy_endpoint_entry_with_resume, envelope_from_v1_report,
    is_safe_relative_path, validate_mutation_capabilities, CopyDirection,
};
use super::transaction_log::TransactionLog;
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
    direction: CopyDirection,
    paths: Vec<String>,
    paths_file: Option<PathBuf>,
    checkpoint_dir: Option<PathBuf>,
    transaction_log: Option<PathBuf>,
    dry_run: bool,
    json: bool,
    schema_version: u8,
) -> Result<(), Box<dyn std::error::Error>> {
    // direction is a typed clap enum; clap already rejected bad values.

    let selected_paths = collect_copy_paths(&paths, paths_file.as_deref())?;
    if selected_paths.is_empty() {
        return Err("no paths selected. Use --path or --paths-file".into());
    }

    let (source_path, target_path) = match direction {
        CopyDirection::LeftToRight => (&left, &right),
        CopyDirection::RightToLeft => (&right, &left),
    };
    let source = build_mutation_endpoint(source_path, false)?;
    let target = build_mutation_endpoint(target_path, true)?;
    validate_mutation_capabilities(&source, false, false, false)?;
    validate_mutation_capabilities(&target, true, false, false)?;

    let mut transaction_log = transaction_log
        .map(|path| TransactionLog::open(path, "copy", source_path, target_path))
        .transpose()?;

    let mut summary = CopySummaryReport {
        total_paths: selected_paths.len(),
        ..CopySummaryReport::default()
    };
    let mut items = Vec::with_capacity(selected_paths.len());

    for rel_path in selected_paths {
        let rel = Path::new(&rel_path);
        if !is_safe_relative_path(rel) {
            if let Some(log) = transaction_log.as_mut() {
                log.action_planned("SKIP", &rel_path, "Invalid relative path")?;
            }
            summary.skipped += 1;
            items.push(CopyItemReport {
                path: rel_path,
                status: "skipped".to_string(),
                detail: "Invalid relative path (must not be absolute or contain '..')".to_string(),
            });
            continue;
        }

        if source.metadata(rel).is_err() {
            if let Some(log) = transaction_log.as_mut() {
                log.action_planned("MISSING", &rel_path, "Source path does not exist")?;
            }
            summary.missing += 1;
            items.push(CopyItemReport {
                path: rel_path,
                status: "missing".to_string(),
                detail: "Source path does not exist".to_string(),
            });
            continue;
        }

        if dry_run {
            if let Some(log) = transaction_log.as_mut() {
                log.action_planned("COPY", &rel_path, "Dry-run: copy planned")?;
            }
            summary.copied += 1;
            items.push(CopyItemReport {
                path: rel_path,
                status: "planned".to_string(),
                detail: format!(
                    "Would copy {} -> {}",
                    source_path.display(),
                    target_path.display()
                ),
            });
            continue;
        }

        if let Some(log) = transaction_log.as_mut() {
            log.action_planned("COPY", &rel_path, "Copy planned")?;
            log.action_started("COPY", &rel_path)?;
        }
        let result =
            copy_endpoint_entry_with_resume(&source, rel, &target, rel, checkpoint_dir.as_deref());
        match result {
            Ok(()) => {
                if let Some(log) = transaction_log.as_mut() {
                    log.action_completed("COPY", &rel_path)?;
                }
                summary.copied += 1;
                items.push(CopyItemReport {
                    path: rel_path,
                    status: "copied".to_string(),
                    detail: "Copied successfully".to_string(),
                });
            }
            Err(e) => {
                if let Some(log) = transaction_log.as_mut() {
                    log.action_failed("COPY", &rel_path, &e.to_string())?;
                }
                summary.failed += 1;
                items.push(CopyItemReport {
                    path: rel_path,
                    status: "failed".to_string(),
                    detail: format!("Copy failed: {e}"),
                });
            }
        }
    }

    if !dry_run {
        if let Err(e) = target.flush() {
            summary.failed += 1;
            items.push(CopyItemReport {
                path: String::new(),
                status: "failed".to_string(),
                detail: format!("Finalizing target failed: {e}"),
            });
        }
    }

    if let Some(log) = transaction_log.as_mut() {
        log.finish(
            summary.missing == 0 && summary.failed == 0,
            &format!(
                "{} copied, {} missing, {} failed",
                summary.copied, summary.missing, summary.failed
            ),
        )?;
    }

    let report = CopyReport {
        schema_version: "1.0.0".to_string(),
        left: left.to_string_lossy().to_string(),
        right: right.to_string_lossy().to_string(),
        direction: direction.as_str().to_string(),
        dry_run,
        summary,
        items,
    };

    if json {
        let report_json = serde_json::to_value(&report)?;
        let output = if schema_version == 1 {
            report_json
        } else {
            envelope_from_v1_report(
                "copy",
                if report.summary.missing > 0 || report.summary.failed > 0 {
                    "partial"
                } else {
                    "completed"
                },
                report_json,
            )
        };
        println!("{}", serde_json::to_string_pretty(&output)?);
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

    if report.summary.missing > 0 || report.summary.failed > 0 {
        return Err(format!(
            "copy completed with {} missing and {} failed item(s)",
            report.summary.missing, report.summary.failed
        )
        .into());
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
