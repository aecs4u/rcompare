//! `sync` command: synchronize two directories using comparison results.
use super::support::{
    apply_copy, apply_delete, run_core_scan, ConflictPolicy, CoreScanOptions, DeleteMode,
    SyncDirection,
};
use rcompare_common::{DiffNode, DiffStatus};
use serde::Serialize;
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

#[derive(Serialize, Clone)]
pub(crate) struct SyncActionReport {
    pub(crate) code: String,
    pub(crate) path: String,
    pub(crate) detail: String,
}

#[derive(Default, Serialize)]
pub(crate) struct SyncSummaryReport {
    pub(crate) total_actions: usize,
    pub(crate) copied: usize,
    pub(crate) updated: usize,
    pub(crate) deleted: usize,
    pub(crate) skipped: usize,
    pub(crate) failed: usize,
}

#[derive(Serialize)]
pub(crate) struct SyncReport {
    pub(crate) schema_version: String,
    pub(crate) left: String,
    pub(crate) right: String,
    pub(crate) direction: String,
    pub(crate) dry_run: bool,
    pub(crate) delete_mode: String,
    pub(crate) conflict_policy: String,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub(crate) warnings: Vec<String>,
    pub(crate) summary: SyncSummaryReport,
    pub(crate) actions: Vec<SyncActionReport>,
}

pub(crate) fn run_sync(
    left: PathBuf,
    right: PathBuf,
    direction: SyncDirection,
    dry_run: bool,
    delete_mode: DeleteMode,
    conflict_policy: ConflictPolicy,
    ignore: Vec<String>,
    follow_symlinks: bool,
    verify_hashes: bool,
    no_verify_hashes: bool,
    cache_dir: Option<PathBuf>,
    strict: bool,
    no_cache: bool,
    cache_read_only: bool,
    hash_jobs: Option<usize>,
    json: bool,
    stop_flag: &Arc<AtomicBool>,
) -> Result<(), Box<dyn std::error::Error>> {
    if !left.is_dir() || !right.is_dir() {
        return Err("sync currently supports local directory paths only".into());
    }

    // direction/delete_mode/conflict_policy are typed clap enums now, so
    // there's nothing left to validate here — clap rejected bad values
    // before this function was ever called.

    // Scan and compare in-process (no subprocess re-exec, no JSON round-trip).
    let scan_opts = CoreScanOptions {
        left: left.clone(),
        right: right.clone(),
        ignore_patterns: ignore,
        follow_symlinks,
        verify_hashes,
        no_verify_hashes,
        cache_dir,
        strict,
        no_cache,
        cache_read_only,
        hash_jobs,
    };
    let scan_result = run_core_scan(&scan_opts, stop_flag)?;

    let actions = plan_sync_actions(&scan_result.diff_nodes, direction, conflict_policy)?;
    let mut summary = SyncSummaryReport {
        total_actions: actions.len(),
        ..SyncSummaryReport::default()
    };

    if dry_run {
        for action in &actions {
            match action.code.as_str() {
                "COPY_LR" | "COPY_RL" => summary.copied += 1,
                "UPDATE_L" | "UPDATE_R" => summary.updated += 1,
                "DELETE_L" | "DELETE_R" => summary.deleted += 1,
                _ => summary.skipped += 1,
            }
        }
    } else {
        execute_sync_actions(&actions, &left, &right, delete_mode, &mut summary);
    }

    let report = SyncReport {
        schema_version: "1.0.0".to_string(),
        left: left.to_string_lossy().to_string(),
        right: right.to_string_lossy().to_string(),
        direction: direction.as_str().to_string(),
        dry_run,
        delete_mode: match delete_mode {
            DeleteMode::Trash => "trash".to_string(),
            DeleteMode::Permanent => "permanent".to_string(),
        },
        conflict_policy: conflict_policy.as_str().to_string(),
        warnings: scan_result.warnings,
        summary,
        actions,
    };

    if json {
        println!("{}", serde_json::to_string_pretty(&report)?);
    } else {
        println!("Synchronization {}", if dry_run { "(dry-run)" } else { "" });
        println!("Left : {}", report.left);
        println!("Right: {}", report.right);
        println!("Mode : {}", report.direction);
        println!(
            "Summary: {} copied, {} updated, {} deleted, {} skipped, {} failed",
            report.summary.copied,
            report.summary.updated,
            report.summary.deleted,
            report.summary.skipped,
            report.summary.failed
        );
        let show = report.actions.len().min(100);
        if show > 0 {
            println!(
                "Planned actions (showing {} of {}):",
                show,
                report.actions.len()
            );
            for action in report.actions.iter().take(show) {
                println!("  [{}] {} -- {}", action.code, action.path, action.detail);
            }
        }
        if !report.warnings.is_empty() {
            println!(
                "\n{} warning{} during scan (pass --strict to fail instead):",
                report.warnings.len(),
                if report.warnings.len() == 1 { "" } else { "s" }
            );
            for warning in report.warnings.iter().take(20) {
                println!("  {warning}");
            }
        }
    }

    Ok(())
}

pub(crate) fn plan_sync_actions(
    entries: &[DiffNode],
    direction: SyncDirection,
    conflict_policy: ConflictPolicy,
) -> Result<Vec<SyncActionReport>, Box<dyn std::error::Error>> {
    let mut refs: Vec<&DiffNode> = entries.iter().collect();
    refs.sort_by(|a, b| a.relative_path.cmp(&b.relative_path));

    let mut actions = Vec::new();
    for entry in refs {
        let status = entry.status;
        let path = entry.relative_path.to_string_lossy().to_string();

        if status == DiffStatus::Same {
            continue;
        }
        if status == DiffStatus::Unchecked {
            actions.push(SyncActionReport {
                code: "SKIP".to_string(),
                path,
                detail: "Unchecked item; manual review required".to_string(),
            });
            continue;
        }

        match direction {
            SyncDirection::LeftToRight => {
                match status {
                    DiffStatus::OrphanLeft => actions.push(SyncActionReport {
                        code: "COPY_LR".to_string(),
                        path,
                        detail: "Create on right".to_string(),
                    }),
                    DiffStatus::OrphanRight => actions.push(SyncActionReport {
                        code: "DELETE_R".to_string(),
                        path,
                        detail: "Delete from right".to_string(),
                    }),
                    DiffStatus::Different => actions.push(SyncActionReport {
                        code: "UPDATE_R".to_string(),
                        path,
                        detail: "Overwrite right from left".to_string(),
                    }),
                    _ => {}
                }
                continue;
            }
            SyncDirection::RightToLeft => {
                match status {
                    DiffStatus::OrphanRight => actions.push(SyncActionReport {
                        code: "COPY_RL".to_string(),
                        path,
                        detail: "Create on left".to_string(),
                    }),
                    DiffStatus::OrphanLeft => actions.push(SyncActionReport {
                        code: "DELETE_L".to_string(),
                        path,
                        detail: "Delete from left".to_string(),
                    }),
                    DiffStatus::Different => actions.push(SyncActionReport {
                        code: "UPDATE_L".to_string(),
                        path,
                        detail: "Overwrite left from right".to_string(),
                    }),
                    _ => {}
                }
                continue;
            }
            SyncDirection::Bidirectional => {}
        }

        // bidirectional
        match status {
            DiffStatus::OrphanLeft => actions.push(SyncActionReport {
                code: "COPY_LR".to_string(),
                path,
                detail: "Missing on right".to_string(),
            }),
            DiffStatus::OrphanRight => actions.push(SyncActionReport {
                code: "COPY_RL".to_string(),
                path,
                detail: "Missing on left".to_string(),
            }),
            DiffStatus::Different => match conflict_policy {
                ConflictPolicy::Left => actions.push(SyncActionReport {
                    code: "COPY_LR".to_string(),
                    path,
                    detail: "Conflict policy=left".to_string(),
                }),
                ConflictPolicy::Right => actions.push(SyncActionReport {
                    code: "COPY_RL".to_string(),
                    path,
                    detail: "Conflict policy=right".to_string(),
                }),
                ConflictPolicy::Skip => actions.push(SyncActionReport {
                    code: "SKIP".to_string(),
                    path,
                    detail: "Conflict policy=skip".to_string(),
                }),
                ConflictPolicy::Error => {
                    return Err(format!("conflict encountered for {path} and policy=error").into());
                }
                ConflictPolicy::Newest => {
                    let left_m = entry.left.as_ref().map(|e| e.modified);
                    let right_m = entry.right.as_ref().map(|e| e.modified);
                    match (left_m, right_m) {
                        (Some(l), Some(r)) if l > r => actions.push(SyncActionReport {
                            code: "COPY_LR".to_string(),
                            path,
                            detail: "Left newer".to_string(),
                        }),
                        (Some(l), Some(r)) if r > l => actions.push(SyncActionReport {
                            code: "COPY_RL".to_string(),
                            path,
                            detail: "Right newer".to_string(),
                        }),
                        _ => actions.push(SyncActionReport {
                            code: "SKIP".to_string(),
                            path,
                            detail: "Cannot determine newer side".to_string(),
                        }),
                    }
                }
            },
            _ => {}
        }
    }
    Ok(actions)
}

pub(crate) fn execute_sync_actions(
    actions: &[SyncActionReport],
    left_root: &Path,
    right_root: &Path,
    delete_mode: DeleteMode,
    summary: &mut SyncSummaryReport,
) {
    for action in actions {
        let rel = Path::new(&action.path);
        let left_path = left_root.join(rel);
        let right_path = right_root.join(rel);

        match action.code.as_str() {
            "COPY_LR" => {
                if apply_copy(&left_path, &right_path).is_ok() {
                    summary.copied += 1;
                } else {
                    summary.failed += 1;
                }
            }
            "COPY_RL" => {
                if apply_copy(&right_path, &left_path).is_ok() {
                    summary.copied += 1;
                } else {
                    summary.failed += 1;
                }
            }
            "UPDATE_R" => {
                if apply_copy(&left_path, &right_path).is_ok() {
                    summary.updated += 1;
                } else {
                    summary.failed += 1;
                }
            }
            "UPDATE_L" => {
                if apply_copy(&right_path, &left_path).is_ok() {
                    summary.updated += 1;
                } else {
                    summary.failed += 1;
                }
            }
            "DELETE_R" => {
                if apply_delete(&right_path, delete_mode).is_ok() {
                    summary.deleted += 1;
                } else {
                    summary.failed += 1;
                }
            }
            "DELETE_L" => {
                if apply_delete(&left_path, delete_mode).is_ok() {
                    summary.deleted += 1;
                } else {
                    summary.failed += 1;
                }
            }
            _ => {
                summary.skipped += 1;
            }
        }
    }
}
