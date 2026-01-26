#![allow(clippy::too_many_arguments)]

use clap::{Parser, Subcommand};
use indicatif::{ProgressBar, ProgressStyle};
use rcompare_common::{default_cache_dir, load_config, DiffStatus, Vfs};
use rcompare_core::vfs::{SevenZVfs, TarVfs, ZipVfs};
use rcompare_core::text_diff::{RegexRule, TextDiffConfig, WhitespaceMode};
use rcompare_core::{
    is_csv_file, is_excel_file, is_image_file, is_json_file, is_parquet_file, is_yaml_file,
    ComparisonEngine, CsvDiffEngine, ExcelDiffEngine, FolderScanner, HashCache, ImageDiffEngine,
    JsonDiffEngine, ParquetDiffEngine, TextDiffEngine,
};
use serde::Serialize;
use std::io::IsTerminal;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

#[derive(Parser)]
#[command(name = "rcompare")]
#[command(author = "RCompare Contributors")]
#[command(version = "0.1.0")]
#[command(about = "High-performance file and directory comparison utility", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Scan and compare two directories
    Scan {
        /// Left directory path
        left: PathBuf,

        /// Right directory path
        right: PathBuf,

        /// Ignore patterns (can be specified multiple times)
        #[arg(short, long)]
        ignore: Vec<String>,

        /// Follow symbolic links
        #[arg(short = 'L', long)]
        follow_symlinks: bool,

        /// Verify file hashes for same-sized files
        #[arg(short = 'v', long)]
        verify_hashes: bool,

        /// Disable file hash verification
        #[arg(long, conflicts_with = "verify_hashes")]
        no_verify_hashes: bool,

        /// Cache directory for hash storage
        #[arg(short, long)]
        cache_dir: Option<PathBuf>,

        /// Show only differences (hide identical files)
        #[arg(short = 'd', long)]
        diff_only: bool,

        /// Hide identical files from output
        #[arg(long)]
        hide_identical: bool,

        /// Hide different files from output
        #[arg(long)]
        hide_different: bool,

        /// Hide left-only files from output
        #[arg(long)]
        hide_left_only: bool,

        /// Hide right-only files from output
        #[arg(long)]
        hide_right_only: bool,

        /// Hide unchecked files from output
        #[arg(long)]
        hide_unchecked: bool,

        /// Output results as JSON
        #[arg(long)]
        json: bool,

        /// Disable ANSI colors in output
        #[arg(long)]
        no_color: bool,

        /// Use columned diff-style output (side-by-side comparison)
        #[arg(long)]
        columns: bool,

        /// Enable image-specific comparison with pixel difference analysis
        #[arg(long)]
        image_diff: bool,

        /// Enable CSV-specific comparison with row-by-row analysis
        #[arg(long)]
        csv_diff: bool,

        /// Enable Excel-specific comparison with sheet and cell analysis
        #[arg(long)]
        excel_diff: bool,

        /// Enable JSON-specific comparison with structural analysis
        #[arg(long)]
        json_diff: bool,

        /// Enable YAML-specific comparison with structural analysis
        #[arg(long)]
        yaml_diff: bool,

        /// Enable Parquet-specific comparison with dataframe analysis
        #[arg(long)]
        parquet_diff: bool,

        /// Enable text-specific comparison with line-by-line diff
        #[arg(long)]
        text_diff: bool,

        /// Ignore whitespace when comparing text files
        /// Options: all, leading, trailing, changes
        #[arg(long, value_name = "MODE")]
        ignore_whitespace: Option<String>,

        /// Ignore case when comparing text files
        #[arg(long)]
        ignore_case: bool,

        /// Apply regex rule to text before comparison (pattern:replacement)
        /// Can be specified multiple times. Format: "pattern:replacement:description"
        #[arg(long, value_name = "RULE")]
        regex_rule: Vec<String>,

        /// Compare EXIF metadata when comparing images
        #[arg(long)]
        image_exif: bool,

        /// Set pixel difference tolerance for image comparison (0-255)
        #[arg(long, value_name = "TOLERANCE", default_value = "1")]
        image_tolerance: u8,
    },
}

enum ArchiveKind {
    Zip,
    Tar,
    SevenZ,
}

enum ScanSource {
    Local { root: PathBuf },
    Vfs { vfs: Box<dyn Vfs>, root: PathBuf },
}

impl ScanSource {
    fn root(&self) -> &std::path::Path {
        match self {
            ScanSource::Local { root } => root.as_path(),
            ScanSource::Vfs { root, .. } => root.as_path(),
        }
    }

    fn vfs(&self) -> Option<&dyn Vfs> {
        match self {
            ScanSource::Vfs { vfs, .. } => Some(vfs.as_ref()),
            _ => None,
        }
    }
}

fn main() {
    // Initialize tracing to stderr (so JSON output can go cleanly to stdout)
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Scan {
            left,
            right,
            ignore,
            follow_symlinks,
            verify_hashes,
            no_verify_hashes,
            cache_dir,
            diff_only,
            hide_identical,
            hide_different,
            hide_left_only,
            hide_right_only,
            hide_unchecked,
            json,
            no_color,
            columns,
            image_diff,
            csv_diff,
            excel_diff,
            json_diff,
            yaml_diff,
            parquet_diff,
            text_diff,
            ignore_whitespace,
            ignore_case,
            regex_rule,
            image_exif,
            image_tolerance,
        } => {
            if let Err(e) = run_scan(
                left,
                right,
                ignore,
                follow_symlinks,
                verify_hashes,
                no_verify_hashes,
                cache_dir,
                diff_only,
                hide_identical,
                hide_different,
                hide_left_only,
                hide_right_only,
                hide_unchecked,
                json,
                no_color,
                columns,
                image_diff,
                csv_diff,
                excel_diff,
                json_diff,
                yaml_diff,
                parquet_diff,
                text_diff,
                ignore_whitespace,
                ignore_case,
                regex_rule,
                image_exif,
                image_tolerance,
            ) {
                error!("Scan failed: {}", e);
                std::process::exit(1);
            }
        }
    }
}

/// Build TextDiffConfig from CLI flags
fn build_text_diff_config(
    ignore_whitespace: Option<String>,
    ignore_case: bool,
    regex_rules: Vec<String>,
) -> Result<TextDiffConfig, Box<dyn std::error::Error>> {
    let mut config = TextDiffConfig::new();

    // Parse whitespace mode
    if let Some(mode) = ignore_whitespace {
        config.whitespace_mode = match mode.to_lowercase().as_str() {
            "all" => WhitespaceMode::IgnoreAll,
            "leading" => WhitespaceMode::IgnoreLeading,
            "trailing" => WhitespaceMode::IgnoreTrailing,
            "changes" => WhitespaceMode::IgnoreChanges,
            _ => {
                return Err(format!(
                    "Invalid whitespace mode '{}'. Valid options: all, leading, trailing, changes",
                    mode
                )
                .into())
            }
        };
    }

    // Set case sensitivity
    config.ignore_case = ignore_case;

    // Parse regex rules
    for rule_str in regex_rules {
        let parts: Vec<&str> = rule_str.splitn(3, ':').collect();
        if parts.len() < 2 {
            return Err(format!(
                "Invalid regex rule format '{}'. Expected 'pattern:replacement:description'",
                rule_str
            )
            .into());
        }

        let pattern = regex::Regex::new(parts[0])?;
        let replacement = parts[1].to_string();
        let description = parts.get(2).unwrap_or(&"").to_string();

        config.regex_rules.push(RegexRule {
            pattern,
            replacement,
            description,
        });
    }

    Ok(config)
}

fn run_scan(
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
) -> Result<(), Box<dyn std::error::Error>> {
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
    if let Some(cache_dir) = cache_dir.clone() {
        config.cache_dir = Some(cache_dir);
    }

    // Determine cache directory
    let cache_path = match config.cache_dir.clone() {
        Some(path) => path,
        None => default_cache_dir(loaded.portable, &loaded.path)?,
    };

    info!("Using cache directory: {}", cache_path.display());

    // Initialize hash cache
    let hash_cache = HashCache::new(cache_path)?;

    // Build text diff configuration from CLI flags
    let text_config = build_text_diff_config(ignore_whitespace, ignore_case, regex_rules)?;

    // Create scanner
    let mut left_scanner = FolderScanner::new(config.clone());
    let mut right_scanner = FolderScanner::new(config);

    // Load .gitignore if present (left side only)
    if left.is_dir() {
        let _ = left_scanner.load_gitignore(&left);
    }
    if right.is_dir() {
        let _ = right_scanner.load_gitignore(&right);
    }

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

    let left_entries = scan_source(&left_scanner, &left_source)?;

    if let Some(pb) = &pb_left {
        pb.finish_with_message(format!(
            "Found {} entries in left source",
            left_entries.len()
        ));
    } else {
        info!("Found {} entries in left source", left_entries.len());
    }

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

    let right_entries = scan_source(&right_scanner, &right_source)?;

    if let Some(pb) = &pb_right {
        pb.finish_with_message(format!(
            "Found {} entries in right source",
            right_entries.len()
        ));
    } else {
        info!("Found {} entries in right source", right_entries.len());
    }

    // Compare directories
    let pb_compare = if show_progress {
        let pb = ProgressBar::new_spinner();
        pb.set_style(
            ProgressStyle::default_spinner()
                .template("{spinner:.green} {msg} [{elapsed_precise}]")
                .unwrap(),
        );
        if verify_hashes {
            pb.set_message("Comparing and hashing files...");
        } else {
            pb.set_message("Comparing files...");
        }
        pb.enable_steady_tick(std::time::Duration::from_millis(100));
        Some(pb)
    } else {
        info!("Comparing directories...");
        None
    };

    let comparison_engine = ComparisonEngine::new(hash_cache).with_hash_verification(verify_hashes);
    let diff_nodes = comparison_engine.compare_with_vfs(
        left_source.root(),
        right_source.root(),
        left_entries,
        right_entries,
        left_source.vfs(),
        right_source.vfs(),
    )?;

    if let Some(pb) = &pb_compare {
        pb.finish_with_message(format!(
            "Comparison complete - {} nodes processed",
            diff_nodes.len()
        ));
    }

    comparison_engine.persist_cache()?;

    if json {
        let report = build_json_report(
            &left,
            &right,
            &diff_nodes,
            diff_only,
            hide_identical,
            hide_different,
            hide_left_only,
            hide_right_only,
            hide_unchecked,
        );
        let output = serde_json::to_string_pretty(&report)?;
        println!("{output}");
        return Ok(());
    }

    // Display results
    let use_color = !no_color && std::io::stdout().is_terminal();

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
    println!("  Identical:       {} {}", same_count, same_mark);
    println!("  Different:       {} {}", different_count, diff_mark);
    println!("  Left only:       {} {}", orphan_left_count, left_mark);
    println!("  Right only:      {} {}", orphan_right_count, right_mark);
    println!("  Unchecked:       {} {}", unchecked_count, unchecked_mark);
    println!("{}", "=".repeat(80));

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

        println!("\n{}", "=".repeat(80));
        println!("Image Comparison Details");
        println!("{}", "=".repeat(80));

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
                                    println!("  {}Similarity: {:.2}%{}", color, similarity, reset);
                                } else {
                                    println!(
                                        "  {}Different dimensions - not comparable{}",
                                        if use_color { "\x1b[33m" } else { "" },
                                        if use_color { "\x1b[0m" } else { "" }
                                    );
                                }
                            }
                            Err(e) => {
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

        if let Some(pb) = &pb_images {
            pb.finish_and_clear();
        }

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

        println!("\n{}", "=".repeat(80));
        println!("CSV Comparison Details");
        println!("{}", "=".repeat(80));

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
                                    for diff in result.row_diffs.iter().take(5)
                                    {
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
                            Err(e) => {
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

        if let Some(pb) = &pb_csvs {
            pb.finish_and_clear();
        }

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

        println!("\n{}", "=".repeat(80));
        println!("Excel Comparison Details");
        println!("{}", "=".repeat(80));

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
                                println!("\n{}", node.relative_path.display());

                                if !result.sheet_names_match {
                                    println!(
                                        "  {}Sheet names differ{}",
                                        if use_color { "\x1b[33m" } else { "" },
                                        if use_color { "\x1b[0m" } else { "" }
                                    );
                                    println!("    Left:  {}", result.left_sheet_names.join(", "));
                                    println!("    Right: {}", result.right_sheet_names.join(", "));
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
                            Err(e) => {
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

        if let Some(pb) = &pb_excel {
            pb.finish_and_clear();
        }

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

        println!("\n{}", "=".repeat(80));
        println!("JSON Comparison Details");
        println!("{}", "=".repeat(80));

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
                            Err(e) => {
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

        if let Some(pb) = &pb_json {
            pb.finish_and_clear();
        }

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

        println!("\n{}", "=".repeat(80));
        println!("YAML Comparison Details");
        println!("{}", "=".repeat(80));

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
                            Err(e) => {
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

        if let Some(pb) = &pb_yaml {
            pb.finish_and_clear();
        }

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
                        Err(e) => {
                            pb.inc(1);
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

            pb.finish_and_clear();
        }

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

        println!("\n{}", "=".repeat(80));
        println!("Text Comparison Details");
        println!("{}", "=".repeat(80));

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
                        match (std::fs::read_to_string(&left_path), std::fs::read_to_string(&right_path)) {
                            (Ok(left_content), Ok(right_content)) => {
                                match text_engine.compare_text_patience(&left_content, &right_content, &left_path) {
                                    Ok(diff_lines) => {
                                        text_comparisons += 1;

                                        // Count different line types
                                        let mut inserted = 0;
                                        let mut deleted = 0;
                                        let mut equal = 0;
                                        for line in &diff_lines {
                                            match line.change_type {
                                                rcompare_core::text_diff::DiffChangeType::Insert => inserted += 1,
                                                rcompare_core::text_diff::DiffChangeType::Delete => deleted += 1,
                                                rcompare_core::text_diff::DiffChangeType::Equal => equal += 1,
                                            }
                                        }

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
                                    Err(e) => {
                                        println!(
                                            "\n{}: Failed to compare - {}",
                                            node.relative_path.display(),
                                            e
                                        );
                                    }
                                }
                            }
                            (Err(e), _) | (_, Err(e)) => {
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

        if let Some(pb) = &pb_texts {
            pb.finish_and_clear();
        }

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

    Ok(())
}

/// Check if a file is likely a text file based on extension
fn is_text_file(path: &Path) -> bool {
    path.extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| {
            matches!(
                ext.to_lowercase().as_str(),
                "txt" | "md" | "markdown" | "rst" | "log"
                | "rs" | "toml" | "yaml" | "yml" | "json" | "xml" | "html" | "htm" | "css" | "js" | "ts" | "tsx" | "jsx"
                | "c" | "cpp" | "cc" | "cxx" | "h" | "hpp" | "hxx" | "cs" | "java" | "py" | "rb" | "go" | "php" | "pl" | "sh" | "bash" | "zsh" | "fish"
                | "sql" | "conf" | "cfg" | "ini" | "properties"
                | "cmake" | "make" | "dockerfile" | "gitignore" | "gitattributes"
            )
        })
        .unwrap_or(false)
}

#[derive(Serialize)]
struct JsonReport {
    left: String,
    right: String,
    summary: JsonSummary,
    entries: Vec<JsonEntry>,
}

#[derive(Serialize)]
struct JsonSummary {
    total: usize,
    same: usize,
    different: usize,
    orphan_left: usize,
    orphan_right: usize,
    unchecked: usize,
}

#[derive(Serialize)]
struct JsonEntry {
    path: String,
    status: DiffStatus,
    left: Option<JsonFileSide>,
    right: Option<JsonFileSide>,
}

#[derive(Serialize)]
struct JsonFileSide {
    size: u64,
    modified_unix: Option<u64>,
    is_dir: bool,
}

fn build_json_report(
    left: &Path,
    right: &Path,
    diff_nodes: &[rcompare_common::DiffNode],
    diff_only: bool,
    hide_identical: bool,
    hide_different: bool,
    hide_left_only: bool,
    hide_right_only: bool,
    hide_unchecked: bool,
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
        left: left.to_string_lossy().to_string(),
        right: right.to_string_lossy().to_string(),
        summary,
        entries,
    }
}

fn json_side(entry: &rcompare_common::FileEntry) -> JsonFileSide {
    JsonFileSide {
        size: entry.size,
        modified_unix: system_time_to_unix(entry.modified),
        is_dir: entry.is_dir,
    }
}

fn system_time_to_unix(time: SystemTime) -> Option<u64> {
    time.duration_since(UNIX_EPOCH).ok().map(|d| d.as_secs())
}

fn truncate_path(path: &str, max_len: usize) -> String {
    if path.chars().count() <= max_len {
        return path.to_string();
    }

    // Try to keep the end of the path (filename) visible
    let prefix = "...";
    let keep_len = max_len.saturating_sub(prefix.len());

    // Use char indices to avoid splitting UTF-8 characters
    let skip_count = path.chars().count().saturating_sub(keep_len);
    let suffix: String = path.chars().skip(skip_count).collect();

    format!("{}{}", prefix, suffix)
}

fn should_show_entry(
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

fn scan_source(
    scanner: &FolderScanner,
    source: &ScanSource,
) -> Result<Vec<rcompare_common::FileEntry>, rcompare_common::RCompareError> {
    match source {
        ScanSource::Local { root } => scanner.scan(root),
        ScanSource::Vfs { vfs, root } => scanner.scan_vfs(vfs.as_ref(), root),
    }
}

fn build_scan_source(path: &std::path::Path) -> Result<ScanSource, Box<dyn std::error::Error>> {
    if path.is_dir() {
        return Ok(ScanSource::Local {
            root: path.to_path_buf(),
        });
    }

    if path.is_file() {
        return match detect_archive_kind(path) {
            Some(ArchiveKind::Zip) => Ok(ScanSource::Vfs {
                vfs: Box::new(ZipVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            Some(ArchiveKind::Tar) => Ok(ScanSource::Vfs {
                vfs: Box::new(TarVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            Some(ArchiveKind::SevenZ) => Ok(ScanSource::Vfs {
                vfs: Box::new(SevenZVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            None => Err(format!(
                "Path is not a directory or supported archive (.zip, .tar, .tar.gz, .tgz, .7z): {}",
                path.display()
            )
            .into()),
        };
    }

    Err(format!("Path does not exist: {}", path.display()).into())
}

fn detect_archive_kind(path: &std::path::Path) -> Option<ArchiveKind> {
    let name = path.file_name()?.to_string_lossy().to_lowercase();
    if name.ends_with(".zip") {
        Some(ArchiveKind::Zip)
    } else if name.ends_with(".tar") || name.ends_with(".tar.gz") || name.ends_with(".tgz") {
        Some(ArchiveKind::Tar)
    } else if name.ends_with(".7z") {
        Some(ArchiveKind::SevenZ)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;
    use std::time::{Duration, UNIX_EPOCH};

    #[test]
    fn test_detect_archive_kind_zip() {
        assert!(matches!(
            detect_archive_kind(Path::new("file.zip")),
            Some(ArchiveKind::Zip)
        ));
        assert!(matches!(
            detect_archive_kind(Path::new("FILE.ZIP")),
            Some(ArchiveKind::Zip)
        ));
        assert!(matches!(
            detect_archive_kind(Path::new("/path/to/archive.ZIP")),
            Some(ArchiveKind::Zip)
        ));
    }

    #[test]
    fn test_detect_archive_kind_tar() {
        assert!(matches!(
            detect_archive_kind(Path::new("file.tar")),
            Some(ArchiveKind::Tar)
        ));
        assert!(matches!(
            detect_archive_kind(Path::new("file.tar.gz")),
            Some(ArchiveKind::Tar)
        ));
        assert!(matches!(
            detect_archive_kind(Path::new("file.tgz")),
            Some(ArchiveKind::Tar)
        ));
        assert!(matches!(
            detect_archive_kind(Path::new("FILE.TAR.GZ")),
            Some(ArchiveKind::Tar)
        ));
    }

    #[test]
    fn test_detect_archive_kind_7z() {
        assert!(matches!(
            detect_archive_kind(Path::new("file.7z")),
            Some(ArchiveKind::SevenZ)
        ));
        assert!(matches!(
            detect_archive_kind(Path::new("FILE.7Z")),
            Some(ArchiveKind::SevenZ)
        ));
    }

    #[test]
    fn test_detect_archive_kind_none() {
        assert!(detect_archive_kind(Path::new("file.txt")).is_none());
        assert!(detect_archive_kind(Path::new("file.rar")).is_none());
        assert!(detect_archive_kind(Path::new("file")).is_none());
        assert!(detect_archive_kind(Path::new("")).is_none());
    }

    #[test]
    fn test_system_time_to_unix() {
        let time = UNIX_EPOCH + Duration::from_secs(1700000000);
        assert_eq!(system_time_to_unix(time), Some(1700000000));

        assert_eq!(system_time_to_unix(UNIX_EPOCH), Some(0));
    }

    #[test]
    fn test_json_side() {
        let entry = rcompare_common::FileEntry {
            path: PathBuf::from("test.txt"),
            size: 1024,
            modified: UNIX_EPOCH + Duration::from_secs(1700000000),
            is_dir: false,
        };

        let side = json_side(&entry);
        assert_eq!(side.size, 1024);
        assert_eq!(side.modified_unix, Some(1700000000));
        assert!(!side.is_dir);
    }

    #[test]
    fn test_json_side_directory() {
        let entry = rcompare_common::FileEntry {
            path: PathBuf::from("subdir"),
            size: 4096,
            modified: UNIX_EPOCH + Duration::from_secs(1600000000),
            is_dir: true,
        };

        let side = json_side(&entry);
        assert_eq!(side.size, 4096);
        assert_eq!(side.modified_unix, Some(1600000000));
        assert!(side.is_dir);
    }

    #[test]
    fn test_build_json_report_basic() {
        let left = PathBuf::from("/left");
        let right = PathBuf::from("/right");

        let diff_nodes = vec![
            rcompare_common::DiffNode {
                relative_path: PathBuf::from("same.txt"),
                status: DiffStatus::Same,
                left: Some(rcompare_common::FileEntry {
                    path: PathBuf::from("same.txt"),
                    size: 100,
                    modified: UNIX_EPOCH,
                    is_dir: false,
                }),
                right: Some(rcompare_common::FileEntry {
                    path: PathBuf::from("same.txt"),
                    size: 100,
                    modified: UNIX_EPOCH,
                    is_dir: false,
                }),
            },
            rcompare_common::DiffNode {
                relative_path: PathBuf::from("diff.txt"),
                status: DiffStatus::Different,
                left: Some(rcompare_common::FileEntry {
                    path: PathBuf::from("diff.txt"),
                    size: 100,
                    modified: UNIX_EPOCH,
                    is_dir: false,
                }),
                right: Some(rcompare_common::FileEntry {
                    path: PathBuf::from("diff.txt"),
                    size: 200,
                    modified: UNIX_EPOCH,
                    is_dir: false,
                }),
            },
        ];

        let report = build_json_report(
            &left,
            &right,
            &diff_nodes,
            false,
            false,
            false,
            false,
            false,
            false,
        );

        assert_eq!(report.left, "/left");
        assert_eq!(report.right, "/right");
        assert_eq!(report.summary.total, 2);
        assert_eq!(report.summary.same, 1);
        assert_eq!(report.summary.different, 1);
        assert_eq!(report.entries.len(), 2);
    }

    #[test]
    fn test_build_json_report_diff_only() {
        let left = PathBuf::from("/left");
        let right = PathBuf::from("/right");

        let diff_nodes = vec![
            rcompare_common::DiffNode {
                relative_path: PathBuf::from("same.txt"),
                status: DiffStatus::Same,
                left: Some(rcompare_common::FileEntry {
                    path: PathBuf::from("same.txt"),
                    size: 100,
                    modified: UNIX_EPOCH,
                    is_dir: false,
                }),
                right: Some(rcompare_common::FileEntry {
                    path: PathBuf::from("same.txt"),
                    size: 100,
                    modified: UNIX_EPOCH,
                    is_dir: false,
                }),
            },
            rcompare_common::DiffNode {
                relative_path: PathBuf::from("orphan.txt"),
                status: DiffStatus::OrphanLeft,
                left: Some(rcompare_common::FileEntry {
                    path: PathBuf::from("orphan.txt"),
                    size: 100,
                    modified: UNIX_EPOCH,
                    is_dir: false,
                }),
                right: None,
            },
        ];

        let report = build_json_report(
            &left,
            &right,
            &diff_nodes,
            true,
            false,
            false,
            false,
            false,
            false,
        );

        // Summary still counts all, but entries only has non-same
        assert_eq!(report.summary.total, 2);
        assert_eq!(report.summary.same, 1);
        assert_eq!(report.summary.orphan_left, 1);
        assert_eq!(report.entries.len(), 1);
        assert_eq!(report.entries[0].path, "orphan.txt");
    }

    #[test]
    fn test_scan_source_root() {
        let source = ScanSource::Local {
            root: PathBuf::from("/test/path"),
        };
        assert_eq!(source.root(), Path::new("/test/path"));
    }

    #[test]
    fn test_scan_source_vfs_none_for_local() {
        let source = ScanSource::Local {
            root: PathBuf::from("/test/path"),
        };
        assert!(source.vfs().is_none());
    }
}
