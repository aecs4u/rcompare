//! `scan` command: scan and compare two directories or supported archives.
use super::support::{
    build_scan_source, build_text_diff_config, is_text_file, OutputOptions, ScanSource,
};
use indicatif::{ProgressBar, ProgressStyle};
use rcompare_common::{default_cache_dir, load_config, DiffStatus};
use rcompare_core::text_diff::DiffChangeType;
use rcompare_core::{
    is_csv_file, is_excel_file, is_image_file, is_json_file, is_parquet_file, is_yaml_file,
    ComparisonEngine, CsvDiffEngine, ExcelDiffEngine, FolderScanner, HashCache, ImageDiffEngine,
    JsonDiffEngine, ParquetDiffEngine, ProgressData, ScanStage, TextDiffEngine,
};
use serde::Serialize;
use std::fs;
use std::io::{IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tracing::info;

/// Result of a scan operation with diff statistics
#[derive(Debug)]
pub(crate) struct ScanResult {
    /// Total number of entries compared
    #[allow(dead_code)]
    pub(crate) total: usize,
    /// Number of identical files/directories
    pub(crate) identical: usize,
    /// Number of different files
    pub(crate) different: usize,
    /// Number of files only in left
    pub(crate) left_only: usize,
    /// Number of files only in right
    pub(crate) right_only: usize,
    /// Number of unchecked files (same size, different timestamp)
    pub(crate) unchecked: usize,
}


impl ScanResult {
    /// Returns true if any differences were found
    pub(crate) fn has_differences(&self) -> bool {
        self.different > 0 || self.left_only > 0 || self.right_only > 0 || self.unchecked > 0
    }

    /// Get appropriate exit code based on scan results
    /// - 0: No differences found (success)
    /// - 2: Differences found
    pub(crate) fn exit_code(&self) -> i32 {
        if self.has_differences() {
            2
        } else {
            0
        }
    }
}


pub(crate) fn run_scan(
    left: PathBuf,
    right: PathBuf,
    ignore_patterns: Vec<String>,
    follow_symlinks: bool,
    verify_hashes: bool,
    no_verify_hashes: bool,
    cache_dir: Option<PathBuf>,
    diff_only: bool,
    hide_identical: bool,
    hide_different: bool,
    hide_left_only: bool,
    hide_right_only: bool,
    hide_unchecked: bool,
    json: bool,
    no_color: bool,
    columns: bool,
    image_diff: bool,
    csv_diff: bool,
    excel_diff: bool,
    json_diff: bool,
    yaml_diff: bool,
    parquet_diff: bool,
    text_diff: bool,
    ignore_whitespace: Option<String>,
    ignore_case: bool,
    regex_rules: Vec<String>,
    image_exif: bool,
    image_tolerance: u8,
    strict: bool,
    no_cache: bool,
    cache_read_only: bool,
    hash_jobs: Option<usize>,
    output_opts: OutputOptions,
    stop_flag: &Arc<AtomicBool>,
) -> Result<ScanResult, Box<dyn std::error::Error>> {
    // --jsonl implies structured (non-human) output for every `if json`
    // branch below, same as --json; the two differ only in the final
    // document-vs-newline-delimited encoding chosen at the very end.
    let json = json || output_opts.jsonl;

    // Validate paths
    if !left.exists() {
        return Err(format!("Left path does not exist: {}", left.display()).into());
    }
    if !right.exists() {
        return Err(format!("Right path does not exist: {}", right.display()).into());
    }

    info!("Comparing:");
    info!("  Left:  {}", left.display());
    info!("  Right: {}", right.display());

    let loaded = load_config(false)?;
    let mut config = loaded.config;

    if !ignore_patterns.is_empty() {
        config.ignore_patterns.extend(ignore_patterns);
    }
    if follow_symlinks {
        config.follow_symlinks = true;
    }
    let verify_hashes = if verify_hashes {
        true
    } else if no_verify_hashes {
        false
    } else {
        config.use_hash_verification
    };
    config.use_hash_verification = verify_hashes;
    if let Some(cache_dir) = cache_dir {
        config.cache_dir = Some(cache_dir);
    }

    // Determine cache directory
    let cache_path = match config.cache_dir.clone() {
        Some(path) => path,
        None => default_cache_dir(loaded.portable, &loaded.path)?,
    };

    // Initialize hash cache, respecting --no-cache / --cache-mode
    let hash_cache = if no_cache {
        info!("Hash cache disabled (--no-cache)");
        HashCache::disabled()
    } else {
        info!("Using cache directory: {}", cache_path.display());
        let mode = if cache_read_only {
            rcompare_core::CacheMode::ReadOnly
        } else {
            rcompare_core::CacheMode::ReadWrite
        };
        HashCache::with_mode(cache_path, mode)?
    };

    // Build text diff configuration from CLI flags
    let text_config = build_text_diff_config(ignore_whitespace, ignore_case, regex_rules)?;

    // Create scanner. Nested .gitignore files are discovered incrementally
    // during the scan itself (see FolderScanner::scan_with_cancel), not in a
    // separate upfront pass.
    let left_scanner = FolderScanner::new(config.clone()).with_strict(strict);
    let right_scanner = FolderScanner::new(config).with_strict(strict);

    // Scan both directories
    let left_source = build_scan_source(&left)?;
    let right_source = build_scan_source(&right)?;

    // Auto-enable hash verification for archive comparisons
    // Archives don't preserve timestamps reliably, so we need hash verification
    let has_archive = matches!(left_source, ScanSource::Vfs { .. })
        || matches!(right_source, ScanSource::Vfs { .. });
    let verify_hashes = if has_archive && !no_verify_hashes {
        true // Force hash verification for archives unless explicitly disabled
    } else {
        verify_hashes
    };

    // Create progress spinner for scanning (only if not JSON output and stderr is terminal)
    let show_progress = !json && std::io::stderr().is_terminal();
    let json_progress = json; // Emit structured JSON progress to stderr in JSON mode

    // Helper: emit structured progress to stderr for GUI consumption
    let emit_json_progress = |stage: ScanStage, done: usize, total: usize| {
        if !json_progress {
            return;
        }
        let data = ProgressData {
            stage,
            stage_index: match stage {
                ScanStage::ScanningLeft => 0,
                ScanStage::ScanningRight => 1,
                ScanStage::Comparing => 2,
                ScanStage::Hashing => 3,
                ScanStage::DiffingFiles => 4,
                ScanStage::SavingCache | ScanStage::Done => 5,
            },
            stage_count: 6,
            entries_done: done,
            entries_total: total,
            bytes_done: 0,
            bytes_total: 0,
        };
        if let Ok(line) = serde_json::to_string(&data) {
            let _ = writeln!(std::io::stderr(), "PROGRESS:{line}");
        }
    };

    emit_json_progress(ScanStage::ScanningLeft, 0, 0);

    let pb_left = if show_progress {
        let pb = ProgressBar::new_spinner();
        pb.set_style(
            ProgressStyle::default_spinner()
                .template("{spinner:.green} {msg}")
                .unwrap(),
        );
        pb.set_message("Scanning left source...");
        pb.enable_steady_tick(std::time::Duration::from_millis(100));
        Some(pb)
    } else {
        info!("Scanning left source...");
        None
    };

    let left_outcome = scan_source(&left_scanner, &left_source, Some(stop_flag.as_ref()))?;
    let left_entries = left_outcome.entries;
    let mut scan_warnings: Vec<String> = left_outcome
        .warnings
        .into_iter()
        .map(|w| format!("{}: {}", w.path.display(), w.message))
        .collect();

    if let Some(pb) = &pb_left {
        pb.finish_with_message(format!(
            "Found {} entries in left source",
            left_entries.len()
        ));
    } else {
        info!("Found {} entries in left source", left_entries.len());
    }

    emit_json_progress(ScanStage::ScanningRight, left_entries.len(), 0);

    let pb_right = if show_progress {
        let pb = ProgressBar::new_spinner();
        pb.set_style(
            ProgressStyle::default_spinner()
                .template("{spinner:.green} {msg}")
                .unwrap(),
        );
        pb.set_message("Scanning right source...");
        pb.enable_steady_tick(std::time::Duration::from_millis(100));
        Some(pb)
    } else {
        info!("Scanning right source...");
        None
    };

    let right_outcome = scan_source(&right_scanner, &right_source, Some(stop_flag.as_ref()))?;
    let right_entries = right_outcome.entries;
    scan_warnings.extend(
        right_outcome
            .warnings
            .into_iter()
            .map(|w| format!("{}: {}", w.path.display(), w.message)),
    );
    for warning in &scan_warnings {
        tracing::warn!("scan warning: {}", warning);
    }

    if let Some(pb) = &pb_right {
        pb.finish_with_message(format!(
            "Found {} entries in right source",
            right_entries.len()
        ));
    } else {
        info!("Found {} entries in right source", right_entries.len());
    }

    // Compare directories
    // Calculate total items to compare
    let total_items = {
        let mut paths: std::collections::HashSet<PathBuf> = std::collections::HashSet::new();
        for entry in &left_entries {
            paths.insert(entry.path.clone());
        }
        for entry in &right_entries {
            paths.insert(entry.path.clone());
        }
        paths.len() as u64
    };

    let pb_compare = if show_progress {
        let pb = ProgressBar::new(total_items);
        pb.set_style(
            ProgressStyle::default_bar()
                .template("{spinner:.green} [{bar:40.cyan/blue}] {pos}/{len} files ({percent}%) [{elapsed_precise}] {msg}")
                .unwrap()
                .progress_chars("#>-"),
        );
        if verify_hashes {
            pb.set_message("Comparing and hashing files...");
        } else {
            pb.set_message("Comparing files...");
        }
        Some(pb)
    } else {
        info!("Comparing directories...");
        None
    };

    let comparison_engine = ComparisonEngine::new(hash_cache)
        .with_hash_verification(verify_hashes)
        .with_hash_concurrency(hash_jobs);

    emit_json_progress(ScanStage::Comparing, 0, total_items as usize);

    // Use progress callback if progress bar or JSON progress is enabled
    let diff_nodes = if pb_compare.is_some() || json_progress {
        let pb_clone = pb_compare.clone();
        let total_for_closure = total_items as usize;
        comparison_engine.compare_with_vfs_and_progress(
            left_source.root(),
            right_source.root(),
            left_entries,
            right_entries,
            left_source.vfs(),
            right_source.vfs(),
            Some(stop_flag.as_ref()),
            Some(move |current, _total| {
                if let Some(ref pb) = pb_clone {
                    pb.set_position(current as u64);
                }
                // Emit JSON progress every ~50 items to avoid flooding stderr
                if json_progress && (current % 50 == 0 || current == total_for_closure) {
                    let data = ProgressData {
                        stage: ScanStage::Comparing,
                        stage_index: 2,
                        stage_count: 6,
                        entries_done: current,
                        entries_total: total_for_closure,
                        bytes_done: 0,
                        bytes_total: 0,
                    };
                    if let Ok(line) = serde_json::to_string(&data) {
                        let _ = writeln!(std::io::stderr(), "PROGRESS:{line}");
                    }
                }
            }),
        )?
    } else {
        comparison_engine.compare_with_vfs_and_cancel(
            left_source.root(),
            right_source.root(),
            left_entries,
            right_entries,
            left_source.vfs(),
            right_source.vfs(),
            Some(stop_flag.as_ref()),
        )?
    };

    if let Some(pb) = &pb_compare {
        pb.finish_with_message(format!(
            "Comparison complete - {} nodes processed",
            diff_nodes.len()
        ));
    }

    emit_json_progress(ScanStage::SavingCache, 0, 0);
    comparison_engine.persist_cache()?;
    emit_json_progress(ScanStage::Done, diff_nodes.len(), diff_nodes.len());

    // Initialize optional result collectors for JSON mode
    let mut json_text_diffs = if json && text_diff {
        Some(Vec::new())
    } else {
        None
    };
    let mut json_image_diffs = if json && image_diff {
        Some(Vec::new())
    } else {
        None
    };
    let mut json_csv_diffs = if json && csv_diff {
        Some(Vec::new())
    } else {
        None
    };
    let mut json_excel_diffs = if json && excel_diff {
        Some(Vec::new())
    } else {
        None
    };
    let mut json_json_diffs = if json && json_diff {
        Some(Vec::new())
    } else {
        None
    };
    let mut json_yaml_diffs = if json && yaml_diff {
        Some(Vec::new())
    } else {
        None
    };
    let mut json_parquet_diffs = if json && parquet_diff {
        Some(Vec::new())
    } else {
        None
    };

    // Display results (text mode only)
    let use_color = !json && !no_color && std::io::stdout().is_terminal();

    if !json {
        let mut same_count = 0;
        let mut different_count = 0;
        let mut orphan_left_count = 0;
        let mut orphan_right_count = 0;
        let mut unchecked_count = 0;

        if columns {
            // Columned output format (side-by-side)
            println!("\n{}", "=".repeat(120));
            println!("Comparison Results (Side-by-Side)");
            println!("{}", "=".repeat(120));
            println!("{:<50} {:^8} {:<50}", "Left", "Status", "Right");
            println!("{}", "-".repeat(120));

            for node in &diff_nodes {
                match node.status {
                    DiffStatus::Same => same_count += 1,
                    DiffStatus::Different => different_count += 1,
                    DiffStatus::OrphanLeft => orphan_left_count += 1,
                    DiffStatus::OrphanRight => orphan_right_count += 1,
                    DiffStatus::Unchecked => unchecked_count += 1,
                }

                // Check if entry should be shown based on filters
                if !should_show_entry(
                    &node.status,
                    diff_only,
                    hide_identical,
                    hide_different,
                    hide_left_only,
                    hide_right_only,
                    hide_unchecked,
                ) {
                    continue;
                }

                let status_symbol = match node.status {
                    DiffStatus::Same => "==",
                    DiffStatus::Different => "!=",
                    DiffStatus::OrphanLeft => "<<",
                    DiffStatus::OrphanRight => ">>",
                    DiffStatus::Unchecked => "??",
                };

                let (status_color, reset) = if use_color {
                    (
                        match node.status {
                            DiffStatus::Same => "\x1b[32m",        // Green
                            DiffStatus::Different => "\x1b[31m",   // Red
                            DiffStatus::OrphanLeft => "\x1b[33m",  // Yellow
                            DiffStatus::OrphanRight => "\x1b[34m", // Blue
                            DiffStatus::Unchecked => "\x1b[36m",   // Cyan
                        },
                        "\x1b[0m",
                    )
                } else {
                    ("", "")
                };

                let left_text = if node.left.is_some() {
                    format!("{}", node.relative_path.display())
                } else {
                    String::from("(missing)")
                };

                let right_text = if node.right.is_some() {
                    format!("{}", node.relative_path.display())
                } else {
                    String::from("(missing)")
                };

                println!(
                    "{:<50} {}{:^8}{} {:<50}",
                    truncate_path(&left_text, 50),
                    status_color,
                    status_symbol,
                    reset,
                    truncate_path(&right_text, 50)
                );
            }
            println!("{}", "=".repeat(120));
        } else {
            // Standard output format
            println!("\n{}", "=".repeat(80));
            println!("Comparison Results");
            println!("{}", "=".repeat(80));

            for node in &diff_nodes {
                match node.status {
                    DiffStatus::Same => same_count += 1,
                    DiffStatus::Different => different_count += 1,
                    DiffStatus::OrphanLeft => orphan_left_count += 1,
                    DiffStatus::OrphanRight => orphan_right_count += 1,
                    DiffStatus::Unchecked => unchecked_count += 1,
                }

                // Check if entry should be shown based on filters
                if !should_show_entry(
                    &node.status,
                    diff_only,
                    hide_identical,
                    hide_different,
                    hide_left_only,
                    hide_right_only,
                    hide_unchecked,
                ) {
                    continue;
                }

                let status_symbol = match node.status {
                    DiffStatus::Same => "  ==  ",
                    DiffStatus::Different => "  !=  ",
                    DiffStatus::OrphanLeft => "  <<  ",
                    DiffStatus::OrphanRight => "  >>  ",
                    DiffStatus::Unchecked => "  ??  ",
                };

                let (status_color, reset) = if use_color {
                    (
                        match node.status {
                            DiffStatus::Same => "\x1b[32m",        // Green
                            DiffStatus::Different => "\x1b[31m",   // Red
                            DiffStatus::OrphanLeft => "\x1b[33m",  // Yellow
                            DiffStatus::OrphanRight => "\x1b[34m", // Blue
                            DiffStatus::Unchecked => "\x1b[36m",   // Cyan
                        },
                        "\x1b[0m",
                    )
                } else {
                    ("", "")
                };

                println!(
                    "{}{}{} {}",
                    status_color,
                    status_symbol,
                    reset,
                    node.relative_path.display()
                );
            }
            println!("\n{}", "=".repeat(80));
        }

        println!("\n{}", "=".repeat(80));
        let same_mark = if use_color {
            "\x1b[32m(==)\x1b[0m"
        } else {
            "(==)"
        };
        let diff_mark = if use_color {
            "\x1b[31m(!=)\x1b[0m"
        } else {
            "(!=)"
        };
        let left_mark = if use_color {
            "\x1b[33m(<<)\x1b[0m"
        } else {
            "(<<)"
        };
        let right_mark = if use_color {
            "\x1b[34m(>>)\x1b[0m"
        } else {
            "(>>)"
        };
        let unchecked_mark = if use_color {
            "\x1b[36m(??)\x1b[0m"
        } else {
            "(??)"
        };

        println!("Summary:");
        println!("  Total entries:   {}", diff_nodes.len());
        println!("  Identical:       {same_count} {same_mark}");
        println!("  Different:       {different_count} {diff_mark}");
        println!("  Left only:       {orphan_left_count} {left_mark}");
        println!("  Right only:      {orphan_right_count} {right_mark}");
        println!("  Unchecked:       {unchecked_count} {unchecked_mark}");
        println!("{}", "=".repeat(80));
    }

    // Image-specific analysis if enabled
    if image_diff {
        let image_engine = ImageDiffEngine::new()
            .with_exif_compare(image_exif)
            .with_tolerance(image_tolerance);

        // Count images to analyze
        let image_count: usize = diff_nodes
            .iter()
            .filter(|node| matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked))
            .filter(|node| {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    is_image_file(&left_entry.path) && is_image_file(&right_entry.path)
                } else {
                    false
                }
            })
            .count();

        let pb_images = if show_progress && image_count > 0 {
            let pb = ProgressBar::new(image_count as u64);
            pb.set_style(
                ProgressStyle::default_bar()
                    .template("{spinner:.green} [{bar:40.cyan/blue}] {pos}/{len} Analyzing images... [{elapsed_precise}<{eta_precise}] ({per_sec})")
                    .unwrap()
                    .progress_chars("#>-")
            );
            Some(pb)
        } else {
            None
        };

        if !json {
            println!("\n{}", "=".repeat(80));
            println!("Image Comparison Details");
            println!("{}", "=".repeat(80));
        }

        let mut image_comparisons = 0;
        for node in &diff_nodes {
            // Only analyze images that exist on both sides and are different/unchecked
            if matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked) {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    if is_image_file(&left_entry.path) && is_image_file(&right_entry.path) {
                        if let Some(pb) = &pb_images {
                            pb.inc(1);
                        }

                        let left_path = left_source.root().join(&left_entry.path);
                        let right_path = right_source.root().join(&right_entry.path);

                        match image_engine.compare_files(&left_path, &right_path) {
                            Ok(result) => {
                                image_comparisons += 1;
                                if json {
                                    if let Some(ref mut diffs) = json_image_diffs {
                                        diffs.push(JsonImageDiffReport {
                                            path: node.relative_path.to_string_lossy().to_string(),
                                            result,
                                        });
                                    }
                                } else {
                                    println!("\n{}", node.relative_path.display());
                                    println!(
                                        "  Dimensions: {}x{} vs {}x{}",
                                        result.left_dimensions.0,
                                        result.left_dimensions.1,
                                        result.right_dimensions.0,
                                        result.right_dimensions.1
                                    );

                                    if result.same_dimensions {
                                        println!(
                                            "  Different pixels: {} ({:.2}%)",
                                            result.different_pixels, result.difference_percentage
                                        );
                                        println!("  Mean pixel diff: {:.2}/255", result.mean_diff);

                                        let similarity = 100.0 - result.difference_percentage;
                                        let (color, reset) = if use_color {
                                            if similarity >= 99.0 {
                                                ("\x1b[32m", "\x1b[0m") // Green
                                            } else if similarity >= 95.0 {
                                                ("\x1b[33m", "\x1b[0m") // Yellow
                                            } else {
                                                ("\x1b[31m", "\x1b[0m") // Red
                                            }
                                        } else {
                                            ("", "")
                                        };
                                        println!(
                                            "  {color}Similarity: {similarity:.2}%{reset}"
                                        );
                                    } else {
                                        println!(
                                            "  {}Different dimensions - not comparable{}",
                                            if use_color { "\x1b[33m" } else { "" },
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }
                                }
                            }
                            Err(e) => {
                                if !json {
                                    println!(
                                        "\n{}: Failed to compare - {}",
                                        node.relative_path.display(),
                                        e
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }

        if let Some(pb) = &pb_images {
            pb.finish_and_clear();
        }

        if !json {
            if image_comparisons > 0 {
                println!("\n{}", "=".repeat(80));
                println!(
                    "Analyzed {} image file{}",
                    image_comparisons,
                    if image_comparisons == 1 { "" } else { "s" }
                );
                println!("{}", "=".repeat(80));
            } else {
                println!("\nNo different images found to analyze.");
                println!("{}", "=".repeat(80));
            }
        }
    }

    // CSV-specific analysis if enabled
    if csv_diff {
        let csv_engine = CsvDiffEngine::new();

        // Count CSVs to analyze
        let csv_count: usize = diff_nodes
            .iter()
            .filter(|node| matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked))
            .filter(|node| {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    is_csv_file(&left_entry.path) && is_csv_file(&right_entry.path)
                } else {
                    false
                }
            })
            .count();

        let pb_csvs = if show_progress && csv_count > 0 {
            let pb = ProgressBar::new(csv_count as u64);
            pb.set_style(
                ProgressStyle::default_bar()
                    .template("{spinner:.green} [{bar:40.cyan/blue}] {pos}/{len} Analyzing CSV files... [{elapsed_precise}<{eta_precise}] ({per_sec})")
                    .unwrap()
                    .progress_chars("#>-")
            );
            Some(pb)
        } else {
            None
        };

        if !json {
            println!("\n{}", "=".repeat(80));
            println!("CSV Comparison Details");
            println!("{}", "=".repeat(80));
        }

        let mut csv_comparisons = 0;
        for node in &diff_nodes {
            // Only analyze CSVs that exist on both sides and are different/unchecked
            if matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked) {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    if is_csv_file(&left_entry.path) && is_csv_file(&right_entry.path) {
                        if let Some(pb) = &pb_csvs {
                            pb.inc(1);
                        }

                        let left_path = left_source.root().join(&left_entry.path);
                        let right_path = right_source.root().join(&right_entry.path);

                        match csv_engine.compare_files(&left_path, &right_path) {
                            Ok(result) => {
                                csv_comparisons += 1;
                                if json {
                                    if let Some(ref mut diffs) = json_csv_diffs {
                                        diffs.push(JsonCsvDiffReport {
                                            path: node.relative_path.to_string_lossy().to_string(),
                                            result,
                                        });
                                    }
                                } else {
                                    println!("\n{}", node.relative_path.display());

                                    if !result.headers_match {
                                        println!(
                                            "  {}Headers differ{}",
                                            if use_color { "\x1b[33m" } else { "" },
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                        println!("    Left:  {}", result.left_headers.join(", "));
                                        println!("    Right: {}", result.right_headers.join(", "));
                                    }

                                    println!("  Total rows: {}", result.total_rows);

                                    if result.identical_rows > 0 {
                                        println!(
                                            "  {}Identical rows: {}{}",
                                            if use_color { "\x1b[32m" } else { "" },
                                            result.identical_rows,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.different_rows > 0 {
                                        println!(
                                            "  {}Modified rows: {}{}",
                                            if use_color { "\x1b[33m" } else { "" },
                                            result.different_rows,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.left_only_rows > 0 {
                                        println!(
                                            "  {}Left-only rows: {}{}",
                                            if use_color { "\x1b[31m" } else { "" },
                                            result.left_only_rows,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.right_only_rows > 0 {
                                        println!(
                                            "  {}Right-only rows: {}{}",
                                            if use_color { "\x1b[34m" } else { "" },
                                            result.right_only_rows,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    // Show first few row differences
                                    if !result.row_diffs.is_empty() {
                                        println!(
                                            "\n  Row-level differences (showing first {}):",
                                            result.row_diffs.len().min(5)
                                        );
                                        for diff in result.row_diffs.iter().take(5) {
                                            match diff.diff_type {
                                                rcompare_core::csv_diff::RowDiffType::Modified => {
                                                    println!(
                                                        "    Row {}: {} modified column(s)",
                                                        diff.row_num,
                                                        diff.column_diffs.len()
                                                    );
                                                    for col_diff in &diff.column_diffs {
                                                        println!(
                                                            "      {} [{}]: {:?} -> {:?}",
                                                            col_diff.column,
                                                            col_diff.index,
                                                            col_diff.left_value,
                                                            col_diff.right_value
                                                        );
                                                    }
                                                }
                                                rcompare_core::csv_diff::RowDiffType::LeftOnly => {
                                                    println!(
                                                        "    Row {}: {}Left only{}",
                                                        diff.row_num,
                                                        if use_color { "\x1b[31m" } else { "" },
                                                        if use_color { "\x1b[0m" } else { "" }
                                                    );
                                                }
                                                rcompare_core::csv_diff::RowDiffType::RightOnly => {
                                                    println!(
                                                        "    Row {}: {}Right only{}",
                                                        diff.row_num,
                                                        if use_color { "\x1b[34m" } else { "" },
                                                        if use_color { "\x1b[0m" } else { "" }
                                                    );
                                                }
                                            }
                                        }
                                        if result.row_diffs.len() > 5 {
                                            println!(
                                                "    ... and {} more row differences",
                                                result.row_diffs.len() - 5
                                            );
                                        }
                                    }
                                }
                            }
                            Err(e) => {
                                if !json {
                                    println!(
                                        "\n{}: Failed to compare - {}",
                                        node.relative_path.display(),
                                        e
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }

        if let Some(pb) = &pb_csvs {
            pb.finish_and_clear();
        }

        if !json {
            if csv_comparisons > 0 {
                println!("\n{}", "=".repeat(80));
                println!(
                    "Analyzed {} CSV file{}",
                    csv_comparisons,
                    if csv_comparisons == 1 { "" } else { "s" }
                );
                println!("{}", "=".repeat(80));
            } else {
                println!("\nNo different CSV files found to analyze.");
                println!("{}", "=".repeat(80));
            }
        }
    }

    // Excel-specific analysis if enabled
    if excel_diff {
        let excel_engine = ExcelDiffEngine::new();

        // Count Excel files to analyze
        let excel_count: usize = diff_nodes
            .iter()
            .filter(|node| matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked))
            .filter(|node| {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    is_excel_file(&left_entry.path) && is_excel_file(&right_entry.path)
                } else {
                    false
                }
            })
            .count();

        let pb_excel = if show_progress && excel_count > 0 {
            let pb = ProgressBar::new(excel_count as u64);
            pb.set_style(
                ProgressStyle::default_bar()
                    .template("{spinner:.green} [{bar:40.cyan/blue}] {pos}/{len} Analyzing Excel files... [{elapsed_precise}<{eta_precise}] ({per_sec})")
                    .unwrap()
                    .progress_chars("#>-")
            );
            Some(pb)
        } else {
            None
        };

        if !json {
            println!("\n{}", "=".repeat(80));
            println!("Excel Comparison Details");
            println!("{}", "=".repeat(80));
        }

        let mut excel_comparisons = 0;
        for node in &diff_nodes {
            // Only analyze Excel files that exist on both sides and are different/unchecked
            if matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked) {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    if is_excel_file(&left_entry.path) && is_excel_file(&right_entry.path) {
                        if let Some(pb) = &pb_excel {
                            pb.inc(1);
                        }

                        let left_path = left_source.root().join(&left_entry.path);
                        let right_path = right_source.root().join(&right_entry.path);

                        match excel_engine.compare_files(&left_path, &right_path) {
                            Ok(result) => {
                                excel_comparisons += 1;
                                if json {
                                    if let Some(ref mut diffs) = json_excel_diffs {
                                        diffs.push(JsonExcelDiffReport {
                                            path: node.relative_path.to_string_lossy().to_string(),
                                            result,
                                        });
                                    }
                                } else {
                                    println!("\n{}", node.relative_path.display());

                                    if !result.sheet_names_match {
                                        println!(
                                            "  {}Sheet names differ{}",
                                            if use_color { "\x1b[33m" } else { "" },
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                        println!(
                                            "    Left:  {}",
                                            result.left_sheet_names.join(", ")
                                        );
                                        println!(
                                            "    Right: {}",
                                            result.right_sheet_names.join(", ")
                                        );
                                    }

                                    println!("  Total sheets: {}", result.total_sheets);

                                    if result.identical_sheets > 0 {
                                        println!(
                                            "  {}Identical sheets: {}{}",
                                            if use_color { "\x1b[32m" } else { "" },
                                            result.identical_sheets,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.different_sheets > 0 {
                                        println!(
                                            "  {}Modified sheets: {}{}",
                                            if use_color { "\x1b[33m" } else { "" },
                                            result.different_sheets,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.left_only_sheets > 0 {
                                        println!(
                                            "  {}Left-only sheets: {}{}",
                                            if use_color { "\x1b[31m" } else { "" },
                                            result.left_only_sheets,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.right_only_sheets > 0 {
                                        println!(
                                            "  {}Right-only sheets: {}{}",
                                            if use_color { "\x1b[34m" } else { "" },
                                            result.right_only_sheets,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    // Show sheet-level differences
                                    if !result.sheet_diffs.is_empty() {
                                        println!(
                                            "\n  Sheet-level differences (showing first {}):",
                                            result.sheet_diffs.len().min(3)
                                        );
                                        for sheet_diff in result.sheet_diffs.iter().take(3) {
                                            match sheet_diff.diff_type {
                                            rcompare_core::excel_diff::SheetDiffType::Modified => {
                                                println!(
                                                    "    Sheet '{}': {}x{}, {} different cell(s)",
                                                    sheet_diff.sheet_name,
                                                    sheet_diff.total_rows,
                                                    sheet_diff.total_cols,
                                                    sheet_diff.different_cells
                                                );

                                                // Show first few cell differences
                                                if !sheet_diff.cell_diffs.is_empty() {
                                                    println!("      Cell differences (showing first {}):", sheet_diff.cell_diffs.len().min(5));
                                                    for cell_diff in
                                                        sheet_diff.cell_diffs.iter().take(5)
                                                    {
                                                        println!(
                                                            "        Cell ({}, {}): {:?} -> {:?}",
                                                            cell_diff.row + 1,
                                                            cell_diff.col + 1,
                                                            cell_diff.left_value,
                                                            cell_diff.right_value
                                                        );
                                                    }
                                                    if sheet_diff.cell_diffs.len() > 5 {
                                                        println!("        ... and {} more cell differences", sheet_diff.cell_diffs.len() - 5);
                                                    }
                                                }
                                            }
                                            rcompare_core::excel_diff::SheetDiffType::LeftOnly => {
                                                println!(
                                                    "    Sheet '{}': {}Left only{}",
                                                    sheet_diff.sheet_name,
                                                    if use_color { "\x1b[31m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" }
                                                );
                                            }
                                            rcompare_core::excel_diff::SheetDiffType::RightOnly => {
                                                println!(
                                                    "    Sheet '{}': {}Right only{}",
                                                    sheet_diff.sheet_name,
                                                    if use_color { "\x1b[34m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" }
                                                );
                                            }
                                        }
                                        }
                                        if result.sheet_diffs.len() > 3 {
                                            println!(
                                                "    ... and {} more sheet differences",
                                                result.sheet_diffs.len() - 3
                                            );
                                        }
                                    }
                                }
                            }
                            Err(e) => {
                                if !json {
                                    println!(
                                        "\n{}: Failed to compare - {}",
                                        node.relative_path.display(),
                                        e
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }

        if let Some(pb) = &pb_excel {
            pb.finish_and_clear();
        }

        if !json {
            if excel_comparisons > 0 {
                println!("\n{}", "=".repeat(80));
                println!(
                    "Analyzed {} Excel file{}",
                    excel_comparisons,
                    if excel_comparisons == 1 { "" } else { "s" }
                );
                println!("{}", "=".repeat(80));
            } else {
                println!("\nNo different Excel files found to analyze.");
                println!("{}", "=".repeat(80));
            }
        }
    }

    // JSON-specific analysis if enabled
    if json_diff {
        let json_engine = JsonDiffEngine::new();

        // Count JSON files to analyze
        let json_count: usize = diff_nodes
            .iter()
            .filter(|node| matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked))
            .filter(|node| {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    is_json_file(&left_entry.path) && is_json_file(&right_entry.path)
                } else {
                    false
                }
            })
            .count();

        let pb_json = if show_progress && json_count > 0 {
            let pb = ProgressBar::new(json_count as u64);
            pb.set_style(
                ProgressStyle::default_bar()
                    .template("{spinner:.green} [{bar:40.cyan/blue}] {pos}/{len} Analyzing JSON files... [{elapsed_precise}<{eta_precise}] ({per_sec})")
                    .unwrap()
                    .progress_chars("#>-")
            );
            Some(pb)
        } else {
            None
        };

        if !json {
            println!("\n{}", "=".repeat(80));
            println!("JSON Comparison Details");
            println!("{}", "=".repeat(80));
        }

        let mut json_comparisons = 0;
        for node in &diff_nodes {
            if matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked) {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    if is_json_file(&left_entry.path) && is_json_file(&right_entry.path) {
                        if let Some(pb) = &pb_json {
                            pb.inc(1);
                        }

                        let left_path = left_source.root().join(&left_entry.path);
                        let right_path = right_source.root().join(&right_entry.path);

                        match json_engine.compare_json_files(&left_path, &right_path) {
                            Ok(result) => {
                                json_comparisons += 1;
                                if json {
                                    if let Some(ref mut diffs) = json_json_diffs {
                                        diffs.push(JsonJsonDiffReport {
                                            path: node.relative_path.to_string_lossy().to_string(),
                                            result,
                                        });
                                    }
                                } else {
                                    println!("\n{}", node.relative_path.display());
                                    println!("  Total paths: {}", result.total_paths);

                                    if result.identical_paths > 0 {
                                        println!(
                                            "  {}Identical paths: {}{}",
                                            if use_color { "\x1b[32m" } else { "" },
                                            result.identical_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.different_paths > 0 {
                                        println!(
                                            "  {}Different paths: {}{}",
                                            if use_color { "\x1b[33m" } else { "" },
                                            result.different_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.left_only_paths > 0 {
                                        println!(
                                            "  {}Left-only paths: {}{}",
                                            if use_color { "\x1b[31m" } else { "" },
                                            result.left_only_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.right_only_paths > 0 {
                                        println!(
                                            "  {}Right-only paths: {}{}",
                                            if use_color { "\x1b[34m" } else { "" },
                                            result.right_only_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    // Show first few path differences
                                    if !result.path_diffs.is_empty() {
                                        println!(
                                            "\n  Path-level differences (showing first {}):",
                                            result.path_diffs.len().min(5)
                                        );
                                        for diff in result.path_diffs.iter().take(5) {
                                            match diff.diff_type {
                                            rcompare_core::json_diff::PathDiffType::ValueDifferent => {
                                                println!(
                                                    "    {}: {} -> {}",
                                                    diff.path, diff.left_value, diff.right_value
                                                );
                                            }
                                            rcompare_core::json_diff::PathDiffType::TypeDifferent => {
                                                println!(
                                                    "    {} ({}type mismatch{}): {} -> {}",
                                                    diff.path,
                                                    if use_color { "\x1b[33m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    diff.left_value,
                                                    diff.right_value
                                                );
                                            }
                                            rcompare_core::json_diff::PathDiffType::LeftOnly => {
                                                println!(
                                                    "    {}: {}Left only{} ({})",
                                                    diff.path,
                                                    if use_color { "\x1b[31m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    diff.left_value
                                                );
                                            }
                                            rcompare_core::json_diff::PathDiffType::RightOnly => {
                                                println!(
                                                    "    {}: {}Right only{} ({})",
                                                    diff.path,
                                                    if use_color { "\x1b[34m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    diff.right_value
                                                );
                                            }
                                        }
                                        }
                                        if result.path_diffs.len() > 5 {
                                            println!(
                                                "    ... and {} more path differences",
                                                result.path_diffs.len() - 5
                                            );
                                        }
                                    }
                                }
                            }
                            Err(e) => {
                                if !json {
                                    println!(
                                        "\n{}: Failed to compare - {}",
                                        node.relative_path.display(),
                                        e
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }

        if let Some(pb) = &pb_json {
            pb.finish_and_clear();
        }

        if !json {
            if json_comparisons > 0 {
                println!("\n{}", "=".repeat(80));
                println!(
                    "Analyzed {} JSON file{}",
                    json_comparisons,
                    if json_comparisons == 1 { "" } else { "s" }
                );
                println!("{}", "=".repeat(80));
            } else {
                println!("\nNo different JSON files found to analyze.");
                println!("{}", "=".repeat(80));
            }
        }
    }

    // YAML-specific analysis if enabled
    if yaml_diff {
        let yaml_engine = JsonDiffEngine::new();

        // Count YAML files to analyze
        let yaml_count: usize = diff_nodes
            .iter()
            .filter(|node| matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked))
            .filter(|node| {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    is_yaml_file(&left_entry.path) && is_yaml_file(&right_entry.path)
                } else {
                    false
                }
            })
            .count();

        let pb_yaml = if show_progress && yaml_count > 0 {
            let pb = ProgressBar::new(yaml_count as u64);
            pb.set_style(
                ProgressStyle::default_bar()
                    .template("{spinner:.green} [{bar:40.cyan/blue}] {pos}/{len} Analyzing YAML files... [{elapsed_precise}<{eta_precise}] ({per_sec})")
                    .unwrap()
                    .progress_chars("#>-")
            );
            Some(pb)
        } else {
            None
        };

        if !json {
            println!("\n{}", "=".repeat(80));
            println!("YAML Comparison Details");
            println!("{}", "=".repeat(80));
        }

        let mut yaml_comparisons = 0;
        for node in &diff_nodes {
            if matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked) {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    if is_yaml_file(&left_entry.path) && is_yaml_file(&right_entry.path) {
                        if let Some(pb) = &pb_yaml {
                            pb.inc(1);
                        }

                        let left_path = left_source.root().join(&left_entry.path);
                        let right_path = right_source.root().join(&right_entry.path);

                        match yaml_engine.compare_yaml_files(&left_path, &right_path) {
                            Ok(result) => {
                                yaml_comparisons += 1;
                                if json {
                                    if let Some(ref mut diffs) = json_yaml_diffs {
                                        diffs.push(JsonJsonDiffReport {
                                            path: node.relative_path.to_string_lossy().to_string(),
                                            result,
                                        });
                                    }
                                } else {
                                    println!("\n{}", node.relative_path.display());
                                    println!("  Total paths: {}", result.total_paths);

                                    if result.identical_paths > 0 {
                                        println!(
                                            "  {}Identical paths: {}{}",
                                            if use_color { "\x1b[32m" } else { "" },
                                            result.identical_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.different_paths > 0 {
                                        println!(
                                            "  {}Different paths: {}{}",
                                            if use_color { "\x1b[33m" } else { "" },
                                            result.different_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.left_only_paths > 0 {
                                        println!(
                                            "  {}Left-only paths: {}{}",
                                            if use_color { "\x1b[31m" } else { "" },
                                            result.left_only_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    if result.right_only_paths > 0 {
                                        println!(
                                            "  {}Right-only paths: {}{}",
                                            if use_color { "\x1b[34m" } else { "" },
                                            result.right_only_paths,
                                            if use_color { "\x1b[0m" } else { "" }
                                        );
                                    }

                                    // Show first few path differences
                                    if !result.path_diffs.is_empty() {
                                        println!(
                                            "\n  Path-level differences (showing first {}):",
                                            result.path_diffs.len().min(5)
                                        );
                                        for diff in result.path_diffs.iter().take(5) {
                                            match diff.diff_type {
                                            rcompare_core::json_diff::PathDiffType::ValueDifferent => {
                                                println!(
                                                    "    {}: {} -> {}",
                                                    diff.path, diff.left_value, diff.right_value
                                                );
                                            }
                                            rcompare_core::json_diff::PathDiffType::TypeDifferent => {
                                                println!(
                                                    "    {} ({}type mismatch{}): {} -> {}",
                                                    diff.path,
                                                    if use_color { "\x1b[33m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    diff.left_value,
                                                    diff.right_value
                                                );
                                            }
                                            rcompare_core::json_diff::PathDiffType::LeftOnly => {
                                                println!(
                                                    "    {}: {}Left only{} ({})",
                                                    diff.path,
                                                    if use_color { "\x1b[31m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    diff.left_value
                                                );
                                            }
                                            rcompare_core::json_diff::PathDiffType::RightOnly => {
                                                println!(
                                                    "    {}: {}Right only{} ({})",
                                                    diff.path,
                                                    if use_color { "\x1b[34m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    diff.right_value
                                                );
                                            }
                                        }
                                        }
                                        if result.path_diffs.len() > 5 {
                                            println!(
                                                "    ... and {} more path differences",
                                                result.path_diffs.len() - 5
                                            );
                                        }
                                    }
                                }
                            }
                            Err(e) => {
                                if !json {
                                    println!(
                                        "\n{}: Failed to compare - {}",
                                        node.relative_path.display(),
                                        e
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }

        if let Some(pb) = &pb_yaml {
            pb.finish_and_clear();
        }

        if !json {
            if yaml_comparisons > 0 {
                println!("\n{}", "=".repeat(80));
                println!(
                    "Analyzed {} YAML file{}",
                    yaml_comparisons,
                    if yaml_comparisons == 1 { "" } else { "s" }
                );
                println!("{}", "=".repeat(80));
            } else {
                println!("\nNo different YAML files found to analyze.");
                println!("{}", "=".repeat(80));
            }
        }
    }

    // Parquet-specific analysis if enabled
    if parquet_diff {
        let parquet_engine = ParquetDiffEngine::new();
        let mut parquet_comparisons = 0;

        // Count Parquet files to analyze
        let parquet_count: usize = diff_nodes
            .iter()
            .filter(|node| matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked))
            .filter(|node| {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    is_parquet_file(&left_entry.path) && is_parquet_file(&right_entry.path)
                } else {
                    false
                }
            })
            .count();

        if parquet_count > 0 {
            let pb = ProgressBar::new(parquet_count as u64);
            pb.set_style(
                ProgressStyle::default_bar()
                    .template("[{elapsed_precise}] {bar:40.cyan/blue} {pos}/{len} {msg}")
                    .unwrap()
                    .progress_chars("=>-"),
            );
            pb.set_message("Analyzing Parquet files...");

            for node in &diff_nodes {
                if !matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked) {
                    continue;
                }

                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    if !is_parquet_file(&left_entry.path) || !is_parquet_file(&right_entry.path) {
                        continue;
                    }

                    let left_path = left.join(&left_entry.path);
                    let right_path = right.join(&right_entry.path);

                    pb.set_message(format!("Analyzing {}...", left_entry.path.display()));

                    match parquet_engine.compare_parquet_files(&left_path, &right_path) {
                        Ok(result) => {
                            parquet_comparisons += 1;
                            pb.inc(1);

                            if json {
                                if let Some(ref mut diffs) = json_parquet_diffs {
                                    diffs.push(JsonParquetDiffReport {
                                        path: node.relative_path.to_string_lossy().to_string(),
                                        result,
                                    });
                                }
                            } else {
                                println!(
                                    "\n{}{}{}",
                                    if use_color { "\x1b[1;36m" } else { "" },
                                    left_entry.path.display(),
                                    if use_color { "\x1b[0m" } else { "" }
                                );

                                // Schema differences
                                if !result.schema_diffs.is_empty() {
                                    println!(
                                        "  {}Schema differences:{} {} difference(s)",
                                        if use_color { "\x1b[1;33m" } else { "" },
                                        if use_color { "\x1b[0m" } else { "" },
                                        result.schema_diffs.len()
                                    );
                                    for diff in result.schema_diffs.iter().take(5) {
                                        match diff.diff_type {
                                        rcompare_core::parquet_diff::SchemaDiffType::LeftOnly => {
                                            println!(
                                                "    Column '{}': {}Left only{} (type: {})",
                                                diff.column,
                                                if use_color { "\x1b[33m" } else { "" },
                                                if use_color { "\x1b[0m" } else { "" },
                                                diff.left_type.as_deref().unwrap_or("unknown")
                                            );
                                        }
                                        rcompare_core::parquet_diff::SchemaDiffType::RightOnly => {
                                            println!(
                                                "    Column '{}': {}Right only{} (type: {})",
                                                diff.column,
                                                if use_color { "\x1b[34m" } else { "" },
                                                if use_color { "\x1b[0m" } else { "" },
                                                diff.right_type.as_deref().unwrap_or("unknown")
                                            );
                                        }
                                        rcompare_core::parquet_diff::SchemaDiffType::TypeDifferent => {
                                            println!(
                                                "    Column '{}': {}Type mismatch{} ({} vs {})",
                                                diff.column,
                                                if use_color { "\x1b[35m" } else { "" },
                                                if use_color { "\x1b[0m" } else { "" },
                                                diff.left_type.as_deref().unwrap_or("unknown"),
                                                diff.right_type.as_deref().unwrap_or("unknown")
                                            );
                                        }
                                    }
                                    }
                                }

                                // Row statistics
                                println!("  Total rows: {}", result.total_rows);
                                println!(
                                    "  {}Identical rows:{} {}",
                                    if use_color { "\x1b[32m" } else { "" },
                                    if use_color { "\x1b[0m" } else { "" },
                                    result.identical_rows
                                );
                                println!(
                                    "  {}Different rows:{} {}",
                                    if use_color { "\x1b[31m" } else { "" },
                                    if use_color { "\x1b[0m" } else { "" },
                                    result.different_rows
                                );
                                println!(
                                    "  {}Left only:{} {}",
                                    if use_color { "\x1b[33m" } else { "" },
                                    if use_color { "\x1b[0m" } else { "" },
                                    result.left_only_rows
                                );
                                println!(
                                    "  {}Right only:{} {}",
                                    if use_color { "\x1b[34m" } else { "" },
                                    if use_color { "\x1b[0m" } else { "" },
                                    result.right_only_rows
                                );

                                // Show sample of row differences
                                if !result.row_diffs.is_empty() {
                                    println!(
                                        "  Sample differences (showing first {} of {}):",
                                        result.row_diffs.len().min(5),
                                        result.different_rows
                                            + result.left_only_rows
                                            + result.right_only_rows
                                    );
                                    for diff in result.row_diffs.iter().take(5) {
                                        match diff.diff_type {
                                        rcompare_core::parquet_diff::RowDiffType::ValueDifferent => {
                                            println!(
                                                "    Row {}/{}: {} modified column(s)",
                                                diff.left_row.unwrap_or(0),
                                                diff.right_row.unwrap_or(0),
                                                diff.column_diffs.len()
                                            );
                                            for col_diff in diff.column_diffs.iter().take(3) {
                                                println!(
                                                    "      {}: {} -> {}",
                                                    col_diff.column,
                                                    col_diff.left_value,
                                                    col_diff.right_value
                                                );
                                            }
                                        }
                                        rcompare_core::parquet_diff::RowDiffType::LeftOnly => {
                                            println!(
                                                "    Row {}: {}Left only{}",
                                                diff.left_row.unwrap_or(0),
                                                if use_color { "\x1b[33m" } else { "" },
                                                if use_color { "\x1b[0m" } else { "" }
                                            );
                                        }
                                        rcompare_core::parquet_diff::RowDiffType::RightOnly => {
                                            println!(
                                                "    Row {}: {}Right only{}",
                                                diff.right_row.unwrap_or(0),
                                                if use_color { "\x1b[34m" } else { "" },
                                                if use_color { "\x1b[0m" } else { "" }
                                            );
                                        }
                                    }
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            pb.inc(1);
                            if !json {
                                println!(
                                    "\n{}Error comparing {}: {}{}",
                                    if use_color { "\x1b[1;31m" } else { "" },
                                    left_entry.path.display(),
                                    e,
                                    if use_color { "\x1b[0m" } else { "" }
                                );
                            }
                        }
                    }
                }
            }

            pb.finish_and_clear();
        }

        if !json {
            if parquet_comparisons > 0 {
                println!("\n{}", "=".repeat(80));
                println!(
                    "Analyzed {} Parquet file{}",
                    parquet_comparisons,
                    if parquet_comparisons == 1 { "" } else { "s" }
                );
                println!("{}", "=".repeat(80));
            } else {
                println!("\nNo different Parquet files found to analyze.");
                println!("{}", "=".repeat(80));
            }
        }
    }

    // Text-specific analysis if enabled
    if text_diff {
        let text_engine = TextDiffEngine::with_config(text_config);

        // Count text files to analyze
        let text_count: usize = diff_nodes
            .iter()
            .filter(|node| matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked))
            .filter(|node| {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    is_text_file(&left_entry.path) && is_text_file(&right_entry.path)
                } else {
                    false
                }
            })
            .count();

        let pb_texts = if show_progress && text_count > 0 {
            let pb = ProgressBar::new(text_count as u64);
            pb.set_style(
                ProgressStyle::default_bar()
                    .template("{spinner:.green} [{bar:40.cyan/blue}] {pos}/{len} Analyzing text files... [{elapsed_precise}<{eta_precise}] ({per_sec})")
                    .unwrap()
                    .progress_chars("#>-")
            );
            Some(pb)
        } else {
            None
        };

        if !json {
            println!("\n{}", "=".repeat(80));
            println!("Text Comparison Details");
            println!("{}", "=".repeat(80));
        }

        let mut text_comparisons = 0;
        for node in &diff_nodes {
            // Only analyze text files that exist on both sides and are different/unchecked
            if matches!(node.status, DiffStatus::Different | DiffStatus::Unchecked) {
                if let (Some(left_entry), Some(right_entry)) = (&node.left, &node.right) {
                    if is_text_file(&left_entry.path) && is_text_file(&right_entry.path) {
                        if let Some(pb) = &pb_texts {
                            pb.inc(1);
                        }

                        let left_path = left.join(&left_entry.path);
                        let right_path = right.join(&right_entry.path);

                        // Read file contents
                        match (
                            std::fs::read_to_string(&left_path),
                            std::fs::read_to_string(&right_path),
                        ) {
                            (Ok(left_content), Ok(right_content)) => {
                                match text_engine.compare_text_patience(
                                    &left_content,
                                    &right_content,
                                    &left_path,
                                ) {
                                    Ok(diff_lines) => {
                                        text_comparisons += 1;

                                        // Count different line types
                                        let mut inserted = 0;
                                        let mut deleted = 0;
                                        let mut equal = 0;
                                        for line in &diff_lines {
                                            match line.change_type {
                                                DiffChangeType::Insert => inserted += 1,
                                                DiffChangeType::Delete => deleted += 1,
                                                DiffChangeType::Equal => equal += 1,
                                            }
                                        }

                                        if json {
                                            if let Some(ref mut diffs) = json_text_diffs {
                                                let total_lines = diff_lines.len();
                                                let lines = super::support::trim_diff_context(
                                                    diff_lines,
                                                    output_opts.context,
                                                );
                                                diffs.push(JsonTextDiffReport {
                                                    path: node
                                                        .relative_path
                                                        .to_string_lossy()
                                                        .to_string(),
                                                    total_lines,
                                                    equal_lines: equal,
                                                    inserted_lines: inserted,
                                                    deleted_lines: deleted,
                                                    lines,
                                                });
                                            }
                                        } else {
                                            println!("\n{}", node.relative_path.display());
                                            println!("  Total lines: {}", diff_lines.len());
                                            println!(
                                                "  {}Equal lines:{} {}",
                                                if use_color { "\x1b[90m" } else { "" },
                                                if use_color { "\x1b[0m" } else { "" },
                                                equal
                                            );

                                            if inserted > 0 {
                                                println!(
                                                    "  {}Inserted lines:{} {}",
                                                    if use_color { "\x1b[32m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    inserted
                                                );
                                            }
                                            if deleted > 0 {
                                                println!(
                                                    "  {}Deleted lines:{} {}",
                                                    if use_color { "\x1b[31m" } else { "" },
                                                    if use_color { "\x1b[0m" } else { "" },
                                                    deleted
                                                );
                                            }
                                        }
                                    }
                                    Err(e) => {
                                        if !json {
                                            println!(
                                                "\n{}: Failed to compare - {}",
                                                node.relative_path.display(),
                                                e
                                            );
                                        }
                                    }
                                }
                            }
                            (Err(e), _) | (_, Err(e)) => {
                                if !json {
                                    println!(
                                        "\n{}: Failed to read - {}",
                                        node.relative_path.display(),
                                        e
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }

        if let Some(pb) = &pb_texts {
            pb.finish_and_clear();
        }

        if !json {
            if text_comparisons > 0 {
                println!("\n{}", "=".repeat(80));
                println!(
                    "Analyzed {} text file{}",
                    text_comparisons,
                    if text_comparisons == 1 { "" } else { "s" }
                );
                println!("{}", "=".repeat(80));
            } else {
                println!("\nNo different text files found to analyze.");
                println!("{}", "=".repeat(80));
            }
        }
    }

    // JSON output at the end (after all diff processing)
    if json {
        let mut report = build_json_report(
            &left,
            &right,
            &diff_nodes,
            scan_warnings.clone(),
            diff_only,
            hide_identical,
            hide_different,
            hide_left_only,
            hide_right_only,
            hide_unchecked,
            json_text_diffs,
            json_image_diffs,
            json_csv_diffs,
            json_excel_diffs,
            json_json_diffs,
            json_yaml_diffs,
            json_parquet_diffs,
        );

        if output_opts.summary_only {
            report.entries.clear();
        } else if let Some(max) = output_opts.max_results {
            report.entries.truncate(max);
        }

        let mut writer: Box<dyn Write> = match &output_opts.output {
            Some(path) => Box::new(std::io::BufWriter::new(fs::File::create(path)?)),
            None => Box::new(std::io::BufWriter::new(std::io::stdout().lock())),
        };

        if output_opts.jsonl {
            #[derive(Serialize)]
            struct JsonlSummaryLine<'a> {
                #[serde(rename = "type")]
                kind: &'static str,
                schema_version: &'a str,
                left: &'a str,
                right: &'a str,
                summary: &'a JsonSummary,
                #[serde(skip_serializing_if = "Vec::is_empty")]
                warnings: &'a Vec<String>,
            }
            #[derive(Serialize)]
            struct JsonlEntryLine<'a> {
                #[serde(rename = "type")]
                kind: &'static str,
                #[serde(flatten)]
                entry: &'a JsonEntry,
            }

            serde_json::to_writer(
                &mut writer,
                &JsonlSummaryLine {
                    kind: "summary",
                    schema_version: &report.schema_version,
                    left: &report.left,
                    right: &report.right,
                    summary: &report.summary,
                    warnings: &report.warnings,
                },
            )?;
            writeln!(writer)?;
            for entry in &report.entries {
                serde_json::to_writer(&mut writer, &JsonlEntryLine { kind: "entry", entry })?;
                writeln!(writer)?;
            }
        } else if output_opts.pretty {
            serde_json::to_writer_pretty(&mut writer, &report)?;
            writeln!(writer)?;
        } else {
            serde_json::to_writer(&mut writer, &report)?;
            writeln!(writer)?;
        }
        writer.flush()?;
    } else if !scan_warnings.is_empty() {
        println!(
            "\n{} warning{} during scan (pass --strict to fail instead):",
            scan_warnings.len(),
            if scan_warnings.len() == 1 { "" } else { "s" }
        );
        for warning in scan_warnings.iter().take(20) {
            println!("  {warning}");
        }
        if scan_warnings.len() > 20 {
            println!("  ... and {} more", scan_warnings.len() - 20);
        }
    }

    // Calculate final statistics for exit code
    let mut scan_result = ScanResult {
        total: diff_nodes.len(),
        identical: 0,
        different: 0,
        left_only: 0,
        right_only: 0,
        unchecked: 0,
    };

    for node in &diff_nodes {
        match node.status {
            DiffStatus::Same => scan_result.identical += 1,
            DiffStatus::Different => scan_result.different += 1,
            DiffStatus::OrphanLeft => scan_result.left_only += 1,
            DiffStatus::OrphanRight => scan_result.right_only += 1,
            DiffStatus::Unchecked => scan_result.unchecked += 1,
        }
    }

    Ok(scan_result)
}


#[derive(Serialize)]
pub(crate) struct JsonReport {
    /// Schema version for JSON output (semver format)
    /// Version 1.0.0: Initial schema with basic comparison results
    /// Version 1.1.0: Added specialized diff reports (text, image, CSV, etc.)
    pub(crate) schema_version: String,
    pub(crate) left: String,
    pub(crate) right: String,
    pub(crate) summary: JsonSummary,
    /// Non-fatal issues encountered while scanning (filesystem races,
    /// permission errors) -- see `FolderScanner`'s race tolerance. Empty
    /// unless something odd happened; always present so consumers don't
    /// need an `Option` check.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(crate) warnings: Vec<String>,
    pub(crate) entries: Vec<JsonEntry>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) text_diffs: Option<Vec<JsonTextDiffReport>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) image_diffs: Option<Vec<JsonImageDiffReport>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) csv_diffs: Option<Vec<JsonCsvDiffReport>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) excel_diffs: Option<Vec<JsonExcelDiffReport>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) json_diffs: Option<Vec<JsonJsonDiffReport>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) yaml_diffs: Option<Vec<JsonJsonDiffReport>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) parquet_diffs: Option<Vec<JsonParquetDiffReport>>,
}


#[derive(Serialize)]
pub(crate) struct JsonSummary {
    pub(crate) total: usize,
    pub(crate) same: usize,
    pub(crate) different: usize,
    pub(crate) orphan_left: usize,
    pub(crate) orphan_right: usize,
    pub(crate) unchecked: usize,
}


#[derive(Serialize)]
pub(crate) struct JsonEntry {
    pub(crate) path: String,
    pub(crate) status: DiffStatus,
    pub(crate) left: Option<JsonFileSide>,
    pub(crate) right: Option<JsonFileSide>,
}


#[derive(Serialize)]
pub(crate) struct JsonFileSide {
    pub(crate) size: u64,
    pub(crate) modified_unix: Option<u64>,
    pub(crate) is_dir: bool,
}


#[derive(Serialize)]
pub(crate) struct JsonTextDiffReport {
    pub(crate) path: String,
    pub(crate) total_lines: usize,
    pub(crate) equal_lines: usize,
    pub(crate) inserted_lines: usize,
    pub(crate) deleted_lines: usize,
    pub(crate) lines: Vec<rcompare_core::text_diff::DiffLine>,
}


#[derive(Serialize)]
pub(crate) struct JsonImageDiffReport {
    pub(crate) path: String,
    pub(crate) result: rcompare_core::ImageDiffResult,
}


#[derive(Serialize)]
pub(crate) struct JsonCsvDiffReport {
    pub(crate) path: String,
    pub(crate) result: rcompare_core::CsvDiffResult,
}


#[derive(Serialize)]
pub(crate) struct JsonExcelDiffReport {
    pub(crate) path: String,
    pub(crate) result: rcompare_core::ExcelDiffResult,
}


#[derive(Serialize)]
pub(crate) struct JsonJsonDiffReport {
    pub(crate) path: String,
    pub(crate) result: rcompare_core::JsonDiffResult,
}


#[derive(Serialize)]
pub(crate) struct JsonParquetDiffReport {
    pub(crate) path: String,
    pub(crate) result: rcompare_core::ParquetDiffResult,
}


pub(crate) fn build_json_report(
    left: &Path,
    right: &Path,
    diff_nodes: &[rcompare_common::DiffNode],
    warnings: Vec<String>,
    diff_only: bool,
    hide_identical: bool,
    hide_different: bool,
    hide_left_only: bool,
    hide_right_only: bool,
    hide_unchecked: bool,
    text_diffs: Option<Vec<JsonTextDiffReport>>,
    image_diffs: Option<Vec<JsonImageDiffReport>>,
    csv_diffs: Option<Vec<JsonCsvDiffReport>>,
    excel_diffs: Option<Vec<JsonExcelDiffReport>>,
    json_diffs: Option<Vec<JsonJsonDiffReport>>,
    yaml_diffs: Option<Vec<JsonJsonDiffReport>>,
    parquet_diffs: Option<Vec<JsonParquetDiffReport>>,
) -> JsonReport {
    let mut summary = JsonSummary {
        total: diff_nodes.len(),
        same: 0,
        different: 0,
        orphan_left: 0,
        orphan_right: 0,
        unchecked: 0,
    };

    let mut entries = Vec::new();

    for node in diff_nodes {
        match node.status {
            DiffStatus::Same => summary.same += 1,
            DiffStatus::Different => summary.different += 1,
            DiffStatus::OrphanLeft => summary.orphan_left += 1,
            DiffStatus::OrphanRight => summary.orphan_right += 1,
            DiffStatus::Unchecked => summary.unchecked += 1,
        }

        if !should_show_entry(
            &node.status,
            diff_only,
            hide_identical,
            hide_different,
            hide_left_only,
            hide_right_only,
            hide_unchecked,
        ) {
            continue;
        }

        entries.push(JsonEntry {
            path: node.relative_path.to_string_lossy().to_string(),
            status: node.status,
            left: node.left.as_ref().map(json_side),
            right: node.right.as_ref().map(json_side),
        });
    }

    JsonReport {
        schema_version: "1.1.0".to_string(),
        left: left.to_string_lossy().to_string(),
        right: right.to_string_lossy().to_string(),
        summary,
        warnings,
        entries,
        text_diffs,
        image_diffs,
        csv_diffs,
        excel_diffs,
        json_diffs,
        yaml_diffs,
        parquet_diffs,
    }
}


pub(crate) fn json_side(entry: &rcompare_common::FileEntry) -> JsonFileSide {
    JsonFileSide {
        size: entry.size,
        modified_unix: system_time_to_unix(entry.modified),
        is_dir: entry.is_dir,
    }
}


pub(crate) fn system_time_to_unix(time: SystemTime) -> Option<u64> {
    time.duration_since(UNIX_EPOCH).ok().map(|d| d.as_secs())
}


pub(crate) fn truncate_path(path: &str, max_len: usize) -> String {
    if path.chars().count() <= max_len {
        return path.to_string();
    }

    // Try to keep the end of the path (filename) visible
    let prefix = "...";
    let keep_len = max_len.saturating_sub(prefix.len());

    // Use char indices to avoid splitting UTF-8 characters
    let skip_count = path.chars().count().saturating_sub(keep_len);
    let suffix: String = path.chars().skip(skip_count).collect();

    format!("{prefix}{suffix}")
}


pub(crate) fn should_show_entry(
    status: &DiffStatus,
    diff_only: bool,
    hide_identical: bool,
    hide_different: bool,
    hide_left_only: bool,
    hide_right_only: bool,
    hide_unchecked: bool,
) -> bool {
    // diff_only overrides hide_identical
    if diff_only && matches!(status, DiffStatus::Same) {
        return false;
    }

    // Check individual hide flags
    match status {
        DiffStatus::Same if hide_identical => false,
        DiffStatus::Different if hide_different => false,
        DiffStatus::OrphanLeft if hide_left_only => false,
        DiffStatus::OrphanRight if hide_right_only => false,
        DiffStatus::Unchecked if hide_unchecked => false,
        _ => true,
    }
}


pub(crate) fn scan_source(
    scanner: &FolderScanner,
    source: &ScanSource,
    cancel: Option<&AtomicBool>,
) -> Result<rcompare_core::ScanOutcome, rcompare_common::RCompareError> {
    match source {
        ScanSource::Local { root } => scanner.scan_with_cancel(root, cancel),
        ScanSource::Vfs { vfs, root } => scanner.scan_vfs_with_cancel(vfs.as_ref(), root, cancel),
    }
}
