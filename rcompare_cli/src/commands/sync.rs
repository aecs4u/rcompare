//! `sync` command: synchronize two directories using comparison results.
use super::support::json_v2_envelope;
use super::support::{
    build_mutation_endpoint, copy_endpoint_entry_with_cancel, envelope_from_v1_report,
    remove_endpoint_entry, run_core_scan, validate_mutation_capabilities, ConflictPolicy,
    CoreScanOptions, DeleteMode, MutationEndpoint, SyncDirection,
};
use super::sync_checkpoint::SyncCheckpoint;
use super::transaction_log::TransactionLog;
use rcompare_common::{DiffNode, DiffStatus};
use serde::Serialize;
use serde_json::json;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
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
    pub(crate) completed: usize,
    pub(crate) remaining: usize,
    pub(crate) cancelled: bool,
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
    pub(crate) checkpoint_id: Option<String>,
    pub(crate) resumed: bool,
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
    checkpoint_dir: Option<PathBuf>,
    resume_checkpoint: Option<String>,
    transaction_log: Option<PathBuf>,
    strict: bool,
    no_cache: bool,
    cache_read_only: bool,
    hash_jobs: Option<usize>,
    scan_jobs: u8,
    json: bool,
    schema_version: u8,
    stop_flag: &Arc<AtomicBool>,
) -> Result<(), Box<dyn std::error::Error>> {
    // direction/delete_mode/conflict_policy are typed clap enums now, so
    // there's nothing left to validate here — clap rejected bad values
    // before this function was ever called.

    let delete_mode_name = match delete_mode {
        DeleteMode::Trash => "trash",
        DeleteMode::Permanent => "permanent",
    };
    let mut checkpoint = if let Some(id) = resume_checkpoint.as_deref() {
        let dir = checkpoint_dir
            .as_deref()
            .ok_or("--resume-checkpoint requires --checkpoint-dir")?;
        let checkpoint = SyncCheckpoint::load(dir, id)?;
        checkpoint
            .validate_resume(
                &left,
                &right,
                direction.as_str(),
                delete_mode_name,
                conflict_policy.as_str(),
                &ignore,
                follow_symlinks,
                verify_hashes,
                no_verify_hashes,
                strict,
            )
            .map_err(|message| format!("cannot resume sync: {message}"))?;
        Some(checkpoint)
    } else {
        None
    };

    // Scan and compare in-process (no subprocess re-exec, no JSON round-trip).
    let scan_opts = CoreScanOptions {
        left: left.clone(),
        right: right.clone(),
        ignore_patterns: ignore.clone(),
        follow_symlinks,
        verify_hashes,
        no_verify_hashes,
        cache_dir,
        strict,
        no_cache,
        cache_read_only,
        hash_jobs,
        scan_jobs,
    };
    let scan_result = run_core_scan(&scan_opts, stop_flag)?;

    let mut actions = plan_sync_actions(&scan_result.diff_nodes, direction, conflict_policy)?;
    let mut summary = SyncSummaryReport {
        total_actions: actions.len(),
        ..SyncSummaryReport::default()
    };

    let left_endpoint = build_mutation_endpoint(&left, true)?;
    let right_endpoint = build_mutation_endpoint(&right, true)?;
    validate_mutation_capabilities(
        &left_endpoint,
        actions
            .iter()
            .any(|a| matches!(a.code.as_str(), "COPY_RL" | "UPDATE_L")),
        actions.iter().any(|a| a.code == "DELETE_L"),
        matches!(delete_mode, DeleteMode::Trash) && actions.iter().any(|a| a.code == "DELETE_L"),
    )?;
    validate_mutation_capabilities(
        &right_endpoint,
        actions
            .iter()
            .any(|a| matches!(a.code.as_str(), "COPY_LR" | "UPDATE_R")),
        actions.iter().any(|a| a.code == "DELETE_R"),
        matches!(delete_mode, DeleteMode::Trash) && actions.iter().any(|a| a.code == "DELETE_R"),
    )?;

    if !dry_run {
        if checkpoint.is_none() {
            checkpoint = checkpoint_dir.as_ref().map(|_| {
                SyncCheckpoint::new(
                    &left,
                    &right,
                    direction.as_str(),
                    delete_mode_name,
                    conflict_policy.as_str(),
                    &ignore,
                    follow_symlinks,
                    verify_hashes,
                    no_verify_hashes,
                    strict,
                )
            });
        }
        if let (Some(dir), Some(saved)) = (checkpoint_dir.as_deref(), checkpoint.as_mut()) {
            saved.status = "running".to_string();
            saved.total_actions = actions.len();
            saved.completed_actions = 0;
            saved.remaining_actions = actions.len();
            saved.failed_actions = 0;
            saved.save(dir)?;
        }
    }

    let mut transaction_log = transaction_log
        .map(|path| TransactionLog::open(path, "sync", &left, &right))
        .transpose()?;
    let mut warnings = scan_result.warnings;
    if let Some(log) = transaction_log.as_mut() {
        for action in &actions {
            log.action_planned(&action.code, &action.path, &action.detail)?;
        }
    }

    if dry_run {
        for action in &actions {
            match action.code.as_str() {
                "COPY_LR" | "COPY_RL" => summary.copied += 1,
                "UPDATE_L" | "UPDATE_R" => summary.updated += 1,
                "DELETE_L" | "DELETE_R" => summary.deleted += 1,
                _ => summary.skipped += 1,
            }
        }
        summary.completed = actions.len();
    } else {
        execute_sync_actions(
            &mut actions,
            &left_endpoint,
            &right_endpoint,
            delete_mode,
            checkpoint_dir.as_deref(),
            &mut summary,
            transaction_log.as_mut(),
            stop_flag,
        );
        if let Err(e) = left_endpoint.flush() {
            summary.failed += 1;
            tracing::error!("failed to finalize left endpoint: {e}");
        }
        if let Err(e) = right_endpoint.flush() {
            summary.failed += 1;
            tracing::error!("failed to finalize right endpoint: {e}");
        }
    }

    if let (Some(dir), Some(saved)) = (checkpoint_dir.as_deref(), checkpoint.as_mut()) {
        saved.status = if summary.cancelled {
            "cancelled"
        } else if summary.failed > 0 {
            "failed"
        } else {
            "completed"
        }
        .to_string();
        saved.total_actions = summary.total_actions;
        saved.completed_actions = summary.completed;
        saved.remaining_actions = summary.remaining;
        saved.failed_actions = summary.failed;
        if let Err(error) = saved.save(dir) {
            warnings.push(format!("could not update sync checkpoint: {error}"));
        }
    }

    if let Some(log) = transaction_log.as_mut() {
        let detail = format!(
            "{} completed, {} remaining, {} copied, {} updated, {} deleted, {} skipped, {} failed",
            summary.completed,
            summary.remaining,
            summary.copied,
            summary.updated,
            summary.deleted,
            summary.skipped,
            summary.failed
        );
        if summary.cancelled {
            log.finish_cancelled(&detail)?;
        } else {
            log.finish(summary.failed == 0, &detail)?;
        }
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
        checkpoint_id: checkpoint.as_ref().map(|saved| saved.id.clone()),
        resumed: resume_checkpoint.is_some(),
        warnings,
        summary,
        actions,
    };

    if json {
        let report_json = serde_json::to_value(&report)?;
        let output = if schema_version == 1 {
            report_json
        } else {
            envelope_from_v1_report(
                "sync",
                if report.summary.cancelled {
                    "cancelled"
                } else if report.summary.failed > 0 || !report.warnings.is_empty() {
                    "partial"
                } else {
                    "completed"
                },
                report_json,
            )
        };
        println!("{}", serde_json::to_string_pretty(&output)?);
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

    if report.summary.failed > 0 {
        return Err(format!(
            "sync completed with {} failed action(s)",
            report.summary.failed
        )
        .into());
    }

    if report.summary.cancelled {
        return Err("sync cancelled; completed actions are preserved".into());
    }

    Ok(())
}

pub(crate) fn list_sync_checkpoints(
    dir: &Path,
    schema_version: u8,
) -> Result<(), Box<dyn std::error::Error>> {
    let checkpoints = SyncCheckpoint::list(dir)?;
    let output = if schema_version == 1 {
        serde_json::to_value(&checkpoints)?
    } else {
        json_v2_envelope(
            "sync-checkpoints",
            "completed",
            json!({ "checkpoint_count": checkpoints.len() }),
            json!({ "checkpoints": checkpoints }),
            Vec::new(),
        )
    };
    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(())
}

pub(crate) fn discard_sync_checkpoint(
    dir: &Path,
    id: &str,
    schema_version: u8,
) -> Result<(), Box<dyn std::error::Error>> {
    SyncCheckpoint::discard(dir, id)?;
    let output = if schema_version == 1 {
        json!({ "discarded": id })
    } else {
        json_v2_envelope(
            "sync-discard",
            "completed",
            json!({ "discarded": 1 }),
            json!({ "discarded_id": id }),
            Vec::new(),
        )
    };
    println!("{}", serde_json::to_string_pretty(&output)?);
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
            SyncDirection::LeftToRight | SyncDirection::MirrorRight => {
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
            SyncDirection::UpdateRight => {
                match status {
                    DiffStatus::OrphanLeft => actions.push(SyncActionReport {
                        code: "COPY_LR".to_string(),
                        path,
                        detail: "Create on right".to_string(),
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
            SyncDirection::RightToLeft | SyncDirection::MirrorLeft => {
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
            SyncDirection::UpdateLeft => {
                match status {
                    DiffStatus::OrphanRight => actions.push(SyncActionReport {
                        code: "COPY_RL".to_string(),
                        path,
                        detail: "Create on left".to_string(),
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
            SyncDirection::Bidirectional | SyncDirection::UpdateBoth => {}
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
    actions: &mut [SyncActionReport],
    left: &MutationEndpoint,
    right: &MutationEndpoint,
    delete_mode: DeleteMode,
    checkpoint_dir: Option<&Path>,
    summary: &mut SyncSummaryReport,
    mut transaction_log: Option<&mut TransactionLog>,
    stop_flag: &AtomicBool,
) {
    let action_count = actions.len();
    for (index, action) in actions.iter_mut().enumerate() {
        if stop_flag.load(Ordering::SeqCst) {
            summary.cancelled = true;
            summary.remaining = action_count - index;
            break;
        }
        let rel = Path::new(&action.path);

        if let Some(log) = transaction_log.as_deref_mut() {
            if let Err(error) = log.action_started(&action.code, &action.path) {
                summary.failed += 1;
                action.detail = format!("{} (journal failed: {error})", action.detail);
                continue;
            }
        }

        let result = match action.code.as_str() {
            "COPY_LR" => copy_endpoint_entry_with_cancel(
                left,
                rel,
                right,
                rel,
                checkpoint_dir,
                Some(stop_flag),
            )
            .map(|()| summary.copied += 1),
            "COPY_RL" => copy_endpoint_entry_with_cancel(
                right,
                rel,
                left,
                rel,
                checkpoint_dir,
                Some(stop_flag),
            )
            .map(|()| summary.copied += 1),
            "UPDATE_R" => copy_endpoint_entry_with_cancel(
                left,
                rel,
                right,
                rel,
                checkpoint_dir,
                Some(stop_flag),
            )
            .map(|()| summary.updated += 1),
            "UPDATE_L" => copy_endpoint_entry_with_cancel(
                right,
                rel,
                left,
                rel,
                checkpoint_dir,
                Some(stop_flag),
            )
            .map(|()| summary.updated += 1),
            "DELETE_R" => {
                remove_endpoint_entry(right, rel, matches!(delete_mode, DeleteMode::Trash))
                    .map(|()| summary.deleted += 1)
            }
            "DELETE_L" => {
                remove_endpoint_entry(left, rel, matches!(delete_mode, DeleteMode::Trash))
                    .map(|()| summary.deleted += 1)
            }
            _ => {
                summary.skipped += 1;
                Ok(())
            }
        };
        if let Err(error) = result {
            if stop_flag.load(Ordering::SeqCst) {
                summary.cancelled = true;
                summary.remaining = action_count - index;
                action.detail = format!("{} (cancelled; safe to resume)", action.detail);
                if let Some(log) = transaction_log.as_deref_mut() {
                    if let Err(journal_error) = log.action_cancelled(&action.code, &action.path) {
                        action.detail =
                            format!("{} (journal failed: {journal_error})", action.detail);
                        summary.failed += 1;
                    }
                }
                break;
            }
            summary.failed += 1;
            action.detail = format!("{} (failed: {error})", action.detail);
            if let Some(log) = transaction_log.as_deref_mut() {
                if let Err(journal_error) =
                    log.action_failed(&action.code, &action.path, &error.to_string())
                {
                    action.detail = format!("{} (journal failed: {journal_error})", action.detail);
                }
            }
        } else if let Some(log) = transaction_log.as_deref_mut() {
            if let Err(error) = log.action_completed(&action.code, &action.path) {
                summary.failed += 1;
                action.detail = format!("{} (journal failed: {error})", action.detail);
            }
            summary.completed += 1;
        } else {
            summary.completed += 1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn cancellation_before_an_action_reports_all_work_as_remaining() {
        let temp = tempfile::tempdir().expect("temporary directory");
        let left_root = temp.path().join("left");
        let right_root = temp.path().join("right");
        fs::create_dir(&left_root).expect("left directory");
        fs::create_dir(&right_root).expect("right directory");
        let left = build_mutation_endpoint(&left_root, true).expect("left endpoint");
        let right = build_mutation_endpoint(&right_root, true).expect("right endpoint");
        let mut actions = vec![
            SyncActionReport {
                code: "COPY_LR".to_string(),
                path: "one.txt".to_string(),
                detail: "Create on right".to_string(),
            },
            SyncActionReport {
                code: "COPY_LR".to_string(),
                path: "two.txt".to_string(),
                detail: "Create on right".to_string(),
            },
        ];
        let mut summary = SyncSummaryReport {
            total_actions: actions.len(),
            ..SyncSummaryReport::default()
        };
        let stop_flag = AtomicBool::new(true);

        execute_sync_actions(
            &mut actions,
            &left,
            &right,
            DeleteMode::Permanent,
            Some(&temp.path().join("checkpoints")),
            &mut summary,
            None,
            &stop_flag,
        );

        assert!(summary.cancelled);
        assert_eq!(summary.completed, 0);
        assert_eq!(summary.remaining, 2);
        assert_eq!(summary.failed, 0);
        assert!(!right_root.join("one.txt").exists());
    }
}
