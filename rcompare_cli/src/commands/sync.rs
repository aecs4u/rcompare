//! `sync` command: synchronize two directories using comparison results.
use super::support::{apply_copy, apply_delete};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::Command as ProcessCommand;

#[derive(Deserialize)]
pub(crate) struct SyncScanSide {
    pub(crate) modified_unix: Option<u64>,
    #[allow(dead_code)]
    pub(crate) is_dir: bool,
}


#[derive(Deserialize)]
pub(crate) struct SyncScanEntry {
    pub(crate) path: String,
    pub(crate) status: String,
    pub(crate) left: Option<SyncScanSide>,
    pub(crate) right: Option<SyncScanSide>,
}


#[derive(Deserialize)]
pub(crate) struct SyncScanReport {
    pub(crate) entries: Vec<SyncScanEntry>,
}


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
    pub(crate) summary: SyncSummaryReport,
    pub(crate) actions: Vec<SyncActionReport>,
}


pub(crate) fn run_sync(
    left: PathBuf,
    right: PathBuf,
    direction: String,
    dry_run: bool,
    delete_mode: String,
    conflict_policy: String,
    ignore: Vec<String>,
    follow_symlinks: bool,
    verify_hashes: bool,
    no_verify_hashes: bool,
    json: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    if !left.is_dir() || !right.is_dir() {
        return Err("sync currently supports local directory paths only".into());
    }

    let direction = direction.to_lowercase();
    if !matches!(
        direction.as_str(),
        "left_to_right" | "right_to_left" | "bidirectional"
    ) {
        return Err("invalid --direction. Use: left_to_right, right_to_left, bidirectional".into());
    }

    let delete_mode = delete_mode.to_lowercase();
    if !matches!(delete_mode.as_str(), "trash" | "permanent") {
        return Err("invalid --delete-mode. Use: trash, permanent".into());
    }

    let conflict_policy = conflict_policy.to_lowercase();
    if !matches!(
        conflict_policy.as_str(),
        "newest" | "left" | "right" | "skip" | "error"
    ) {
        return Err("invalid --conflict. Use: newest, left, right, skip, error".into());
    }

    let scan_report = run_scan_for_sync(
        &left,
        &right,
        &ignore,
        follow_symlinks,
        verify_hashes,
        no_verify_hashes,
    )?;

    let actions = plan_sync_actions(&scan_report.entries, &direction, &conflict_policy)?;
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
        execute_sync_actions(&actions, &left, &right, &delete_mode, &mut summary);
    }

    let report = SyncReport {
        schema_version: "1.0.0".to_string(),
        left: left.to_string_lossy().to_string(),
        right: right.to_string_lossy().to_string(),
        direction,
        dry_run,
        delete_mode,
        conflict_policy,
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
            println!("Planned actions (showing {} of {}):", show, report.actions.len());
            for action in report.actions.iter().take(show) {
                println!("  [{}] {} -- {}", action.code, action.path, action.detail);
            }
        }
    }

    Ok(())
}


pub(crate) fn run_scan_for_sync(
    left: &Path,
    right: &Path,
    ignore: &[String],
    follow_symlinks: bool,
    verify_hashes: bool,
    no_verify_hashes: bool,
) -> Result<SyncScanReport, Box<dyn std::error::Error>> {
    let exe = std::env::current_exe()?;
    let mut cmd = ProcessCommand::new(exe);
    cmd.arg("scan")
        .arg(left)
        .arg(right)
        .arg("--json");

    if follow_symlinks {
        cmd.arg("--follow-symlinks");
    }
    if verify_hashes {
        cmd.arg("--verify-hashes");
    }
    if no_verify_hashes {
        cmd.arg("--no-verify-hashes");
    }
    for pat in ignore {
        cmd.arg("--ignore").arg(pat);
    }

    let output = cmd.output()?;
    let exit = output.status.code().unwrap_or(1);
    if !matches!(exit, 0 | 2) {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("scan failed (exit {}): {}", exit, stderr.trim()).into());
    }

    let report: SyncScanReport = serde_json::from_slice(&output.stdout)?;
    Ok(report)
}


pub(crate) fn plan_sync_actions(
    entries: &[SyncScanEntry],
    direction: &str,
    conflict_policy: &str,
) -> Result<Vec<SyncActionReport>, Box<dyn std::error::Error>> {
    let mut refs: Vec<&SyncScanEntry> = entries.iter().collect();
    refs.sort_by(|a, b| a.path.cmp(&b.path));

    let mut actions = Vec::new();
    for entry in refs {
        let status = entry.status.as_str();
        if status == "Same" {
            continue;
        }
        if status == "Unchecked" {
            actions.push(SyncActionReport {
                code: "SKIP".to_string(),
                path: entry.path.clone(),
                detail: "Unchecked item; manual review required".to_string(),
            });
            continue;
        }

        if direction == "left_to_right" {
            match status {
                "OrphanLeft" => actions.push(SyncActionReport {
                    code: "COPY_LR".to_string(),
                    path: entry.path.clone(),
                    detail: "Create on right".to_string(),
                }),
                "OrphanRight" => actions.push(SyncActionReport {
                    code: "DELETE_R".to_string(),
                    path: entry.path.clone(),
                    detail: "Delete from right".to_string(),
                }),
                "Different" => actions.push(SyncActionReport {
                    code: "UPDATE_R".to_string(),
                    path: entry.path.clone(),
                    detail: "Overwrite right from left".to_string(),
                }),
                _ => {}
            }
            continue;
        }

        if direction == "right_to_left" {
            match status {
                "OrphanRight" => actions.push(SyncActionReport {
                    code: "COPY_RL".to_string(),
                    path: entry.path.clone(),
                    detail: "Create on left".to_string(),
                }),
                "OrphanLeft" => actions.push(SyncActionReport {
                    code: "DELETE_L".to_string(),
                    path: entry.path.clone(),
                    detail: "Delete from left".to_string(),
                }),
                "Different" => actions.push(SyncActionReport {
                    code: "UPDATE_L".to_string(),
                    path: entry.path.clone(),
                    detail: "Overwrite left from right".to_string(),
                }),
                _ => {}
            }
            continue;
        }

        // bidirectional
        match status {
            "OrphanLeft" => actions.push(SyncActionReport {
                code: "COPY_LR".to_string(),
                path: entry.path.clone(),
                detail: "Missing on right".to_string(),
            }),
            "OrphanRight" => actions.push(SyncActionReport {
                code: "COPY_RL".to_string(),
                path: entry.path.clone(),
                detail: "Missing on left".to_string(),
            }),
            "Different" => match conflict_policy {
                "left" => actions.push(SyncActionReport {
                    code: "COPY_LR".to_string(),
                    path: entry.path.clone(),
                    detail: "Conflict policy=left".to_string(),
                }),
                "right" => actions.push(SyncActionReport {
                    code: "COPY_RL".to_string(),
                    path: entry.path.clone(),
                    detail: "Conflict policy=right".to_string(),
                }),
                "skip" => actions.push(SyncActionReport {
                    code: "SKIP".to_string(),
                    path: entry.path.clone(),
                    detail: "Conflict policy=skip".to_string(),
                }),
                "error" => {
                    return Err(
                        format!("conflict encountered for {} and policy=error", entry.path).into(),
                    );
                }
                "newest" => {
                    let left_m = entry.left.as_ref().and_then(|s| s.modified_unix);
                    let right_m = entry.right.as_ref().and_then(|s| s.modified_unix);
                    match (left_m, right_m) {
                        (Some(l), Some(r)) if l > r => actions.push(SyncActionReport {
                            code: "COPY_LR".to_string(),
                            path: entry.path.clone(),
                            detail: "Left newer".to_string(),
                        }),
                        (Some(l), Some(r)) if r > l => actions.push(SyncActionReport {
                            code: "COPY_RL".to_string(),
                            path: entry.path.clone(),
                            detail: "Right newer".to_string(),
                        }),
                        _ => actions.push(SyncActionReport {
                            code: "SKIP".to_string(),
                            path: entry.path.clone(),
                            detail: "Cannot determine newer side".to_string(),
                        }),
                    }
                }
                _ => {}
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
    delete_mode: &str,
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
