#![allow(clippy::too_many_arguments)]
#![allow(clippy::needless_pass_by_value)] // Will be resolved when functions take config structs (Phase 2b)
#![allow(clippy::unwrap_used)] // CLI uses Box<dyn Error> / anyhow; unwraps are on infallible operations
#![allow(clippy::branches_sharing_code)] // Diff output blocks intentionally keep branches explicit
#![allow(clippy::trivially_copy_pass_by_ref)] // Will be resolved with config struct refactor (Phase 2b)
#![allow(clippy::wildcard_imports)] // commands::* globs are consumed by both main()'s dispatch and the tests module below

mod commands;

use clap::{Parser, Subcommand};
#[cfg(test)]
use rcompare_common::DiffStatus;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

use commands::capabilities::*;
use commands::copy::*;
use commands::diff_file::*;
use commands::read::*;
use commands::scan::*;
#[cfg_attr(not(test), allow(unused_imports))]
use commands::support::*;
use commands::sync::*;

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

        /// Limit embedded text-diff JSON output to N lines of context around
        /// each change instead of every equal line (unified-diff style).
        /// Only affects --text-diff --json output.
        #[arg(long, value_name = "N")]
        context: Option<usize>,

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

        /// Fail immediately on filesystem races/permission errors instead of
        /// collecting them as warnings and continuing
        #[arg(long)]
        strict: bool,

        /// Disable the hash cache entirely (no reads or writes)
        #[arg(long, conflicts_with = "cache_read_only")]
        no_cache: bool,

        /// Read existing cache entries but never write new ones
        #[arg(long)]
        cache_read_only: bool,

        /// Bound the number of threads used for parallel hash verification
        /// (default: one per CPU core)
        #[arg(long, value_name = "N")]
        hash_jobs: Option<usize>,

        /// Pretty-print JSON output (default is compact, one document)
        #[arg(long)]
        pretty: bool,

        /// Emit newline-delimited JSON instead of a single document: one
        /// summary line followed by one line per entry. Useful for streaming
        /// large result sets incrementally (e.g. into the Qt GUI).
        #[arg(long, conflicts_with = "json")]
        jsonl: bool,

        /// Omit the entries list from output; print only summary counts
        #[arg(long)]
        summary_only: bool,

        /// Cap the number of entries included in output
        #[arg(long, value_name = "N")]
        max_results: Option<usize>,

        /// Write output to this file instead of stdout
        #[arg(long, value_name = "PATH")]
        output: Option<PathBuf>,
    },

    /// Synchronize two directories using comparison results
    Sync {
        /// Left directory path
        left: PathBuf,

        /// Right directory path
        right: PathBuf,

        /// Direction: left_to_right, right_to_left, bidirectional
        #[arg(long, default_value = "left_to_right")]
        direction: String,

        /// Dry-run mode (plan only, no filesystem changes)
        #[arg(long)]
        dry_run: bool,

        /// Delete handling mode: trash or permanent
        #[arg(long, default_value = "trash")]
        delete_mode: String,

        /// Conflict policy for bidirectional different files: newest, left, right, skip, error
        #[arg(long, default_value = "newest")]
        conflict: String,

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

        /// Fail immediately on filesystem races/permission errors instead of
        /// collecting them as warnings and continuing
        #[arg(long)]
        strict: bool,

        /// Disable the hash cache entirely (no reads or writes)
        #[arg(long, conflicts_with = "cache_read_only")]
        no_cache: bool,

        /// Read existing cache entries but never write new ones
        #[arg(long)]
        cache_read_only: bool,

        /// Bound the number of threads used for parallel hash verification
        /// (default: one per CPU core)
        #[arg(long, value_name = "N")]
        hash_jobs: Option<usize>,

        /// Output results as JSON
        #[arg(long)]
        json: bool,
    },

    /// Copy selected relative paths between left and right directories
    Copy {
        /// Left directory path
        left: PathBuf,

        /// Right directory path
        right: PathBuf,

        /// Direction: left_to_right, right_to_left
        #[arg(long, default_value = "left_to_right")]
        direction: String,

        /// Relative path to copy (can be provided multiple times)
        #[arg(long = "path", value_name = "REL_PATH")]
        paths: Vec<String>,

        /// File containing relative paths to copy (one per line)
        #[arg(long)]
        paths_file: Option<PathBuf>,

        /// Dry-run mode (plan only, no filesystem changes)
        #[arg(long)]
        dry_run: bool,

        /// Output results as JSON
        #[arg(long)]
        json: bool,
    },

    /// Compute an on-demand diff for one relative file path
    DiffFile {
        /// Left source path (directory or supported archive)
        left: PathBuf,

        /// Right source path (directory or supported archive)
        right: PathBuf,

        /// Relative path inside left/right source
        #[arg(long)]
        path: String,

        /// Diff mode: auto, text, binary, image, csv, excel, json, yaml, parquet
        #[arg(long, default_value = "auto")]
        mode: String,

        /// Output JSON report
        #[arg(long)]
        json: bool,

        /// Ignore whitespace for text mode: all, leading, trailing, changes
        #[arg(long, value_name = "MODE")]
        ignore_whitespace: Option<String>,

        /// Ignore case when comparing text files
        #[arg(long)]
        ignore_case: bool,

        /// Regex rewrite rules for text mode (pattern:replacement:description)
        #[arg(long, value_name = "RULE")]
        regex_rule: Vec<String>,

        /// Compare EXIF metadata in image mode
        #[arg(long)]
        image_exif: bool,

        /// Pixel tolerance for image mode
        #[arg(long, value_name = "TOLERANCE", default_value = "1")]
        image_tolerance: u8,

        /// Maximum number of binary mismatch ranges to emit
        #[arg(long, default_value = "2000")]
        max_binary_ranges: usize,
    },

    /// Read one file from a side and write to stdout or --out path
    Read {
        /// Left source path (directory or supported archive)
        left: PathBuf,

        /// Right source path (directory or supported archive)
        right: PathBuf,

        /// Which source side to read from: left or right
        #[arg(long)]
        side: String,

        /// Relative path inside selected source
        #[arg(long)]
        path: String,

        /// Output file path (defaults to stdout when omitted)
        #[arg(long)]
        out: Option<PathBuf>,
    },

    /// Show supported commands, flags, and schema versions
    Capabilities {
        /// Output capabilities as JSON
        #[arg(long)]
        json: bool,
    },
}

fn main() {
    // Reset SIGPIPE to default behavior so piping to `head` etc. exits cleanly
    #[cfg(unix)]
    {
        // SAFETY: Resetting SIGPIPE to default behavior is safe and standard practice
        // for CLI tools that may be piped to `head`, `less`, etc. Without this, broken
        // pipe errors would surface as panics instead of clean exits.
        unsafe {
            libc::signal(libc::SIGPIPE, libc::SIG_DFL);
        }
    }

    // Capture panics to the log before unwinding
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let payload = if let Some(s) = info.payload().downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = info.payload().downcast_ref::<String>() {
            s.clone()
        } else {
            "unknown panic".to_string()
        };
        let location = info
            .location()
            .map(|l| format!(" at {}:{}:{}", l.file(), l.line(), l.column()))
            .unwrap_or_default();
        eprintln!("rcompare panicked: {payload}{location}");
        default_hook(info);
    }));

    // Initialize tracing to stderr (so JSON output can go cleanly to stdout)
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    // Set up Ctrl-C handler with graceful shutdown
    let stop_flag = Arc::new(AtomicBool::new(false));
    let stop_flag_handler = Arc::clone(&stop_flag);
    ctrlc::set_handler(move || {
        if stop_flag_handler.load(Ordering::SeqCst) {
            // Second Ctrl-C: force exit immediately
            info!("Second Ctrl-C received, forcing exit");
            std::process::exit(130);
        }
        info!("Ctrl-C received, stopping gracefully...");
        stop_flag_handler.store(true, Ordering::SeqCst);
    })
    .expect("Error setting Ctrl-C handler");

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
            context,
            ignore_whitespace,
            ignore_case,
            regex_rule,
            image_exif,
            image_tolerance,
            strict,
            no_cache,
            cache_read_only,
            hash_jobs,
            pretty,
            jsonl,
            summary_only,
            max_results,
            output,
        } => {
            let output_opts = OutputOptions {
                pretty,
                jsonl,
                summary_only,
                max_results,
                output,
                context,
            };
            match run_scan(
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
                strict,
                no_cache,
                cache_read_only,
                hash_jobs,
                output_opts,
                &stop_flag,
            ) {
                Ok(scan_result) => {
                    // Exit with appropriate code based on scan results
                    // 0: No differences found
                    // 2: Differences found
                    std::process::exit(scan_result.exit_code());
                }
                Err(e) => {
                    error!("Scan failed: {}", e);
                    std::process::exit(1);
                }
            }
        }
        Commands::Capabilities { json } => {
            if let Err(e) = run_capabilities(json) {
                error!("Capabilities failed: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Sync {
            left,
            right,
            direction,
            dry_run,
            delete_mode,
            conflict,
            ignore,
            follow_symlinks,
            verify_hashes,
            no_verify_hashes,
            cache_dir,
            strict,
            no_cache,
            cache_read_only,
            hash_jobs,
            json,
        } => {
            if let Err(e) = run_sync(
                left,
                right,
                direction,
                dry_run,
                delete_mode,
                conflict,
                ignore,
                follow_symlinks,
                verify_hashes,
                no_verify_hashes,
                cache_dir,
                strict,
                no_cache,
                cache_read_only,
                hash_jobs,
                json,
                &stop_flag,
            ) {
                error!("Sync failed: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Copy {
            left,
            right,
            direction,
            paths,
            paths_file,
            dry_run,
            json,
        } => {
            if let Err(e) = run_copy(left, right, direction, paths, paths_file, dry_run, json) {
                error!("Copy failed: {}", e);
                std::process::exit(1);
            }
        }
        Commands::DiffFile {
            left,
            right,
            path,
            mode,
            json,
            ignore_whitespace,
            ignore_case,
            regex_rule,
            image_exif,
            image_tolerance,
            max_binary_ranges,
        } => {
            if let Err(e) = run_diff_file(
                left,
                right,
                path,
                mode,
                json,
                ignore_whitespace,
                ignore_case,
                regex_rule,
                image_exif,
                image_tolerance,
                max_binary_ranges,
            ) {
                error!("diff-file failed: {}", e);
                std::process::exit(1);
            }
        }
        Commands::Read {
            left,
            right,
            side,
            path,
            out,
        } => {
            if let Err(e) = run_read(left, right, side, path, out) {
                error!("read failed: {}", e);
                std::process::exit(1);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
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
            Vec::new(),
            false,
            false,
            false,
            false,
            false,
            false,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
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
            Vec::new(),
            true,
            false,
            false,
            false,
            false,
            false,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
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

    #[test]
    fn test_build_capabilities_report_has_core_commands() {
        let report = build_capabilities_report();

        assert_eq!(report.schema_version, "1.0.0");
        assert_eq!(report.scan_json_schema_versions, vec!["1.1.0".to_string()]);
        assert!(report.commands.iter().any(|c| c.name == "scan"));
        assert!(report.commands.iter().any(|c| c.name == "sync"));
        assert!(report.commands.iter().any(|c| c.name == "copy"));
        assert!(report.commands.iter().any(|c| c.name == "diff-file"));
        assert!(report.commands.iter().any(|c| c.name == "read"));
        assert!(report.commands.iter().any(|c| c.name == "capabilities"));
        assert!(report.exit_codes.iter().any(|e| e.code == 2));
    }

    #[test]
    fn test_build_capabilities_report_scan_flags_include_json() {
        let report = build_capabilities_report();
        let scan = report
            .commands
            .iter()
            .find(|c| c.name == "scan")
            .expect("scan command must exist");
        assert!(scan.flags.iter().any(|f| f == "--json"));
        assert!(scan.supports_json);
    }

    fn sync_test_entry(
        path: &str,
        status: DiffStatus,
        left_modified_secs: Option<u64>,
        right_modified_secs: Option<u64>,
    ) -> rcompare_common::DiffNode {
        rcompare_common::DiffNode {
            relative_path: PathBuf::from(path),
            status,
            left: left_modified_secs.map(|secs| rcompare_common::FileEntry {
                path: PathBuf::from(path),
                size: 0,
                modified: UNIX_EPOCH + std::time::Duration::from_secs(secs),
                is_dir: false,
            }),
            right: right_modified_secs.map(|secs| rcompare_common::FileEntry {
                path: PathBuf::from(path),
                size: 0,
                modified: UNIX_EPOCH + std::time::Duration::from_secs(secs),
                is_dir: false,
            }),
        }
    }

    #[test]
    fn test_plan_sync_actions_left_to_right() {
        let entries = vec![
            sync_test_entry("a.txt", DiffStatus::OrphanLeft, Some(10), None),
            sync_test_entry("b.txt", DiffStatus::Different, Some(20), Some(15)),
        ];

        let actions = plan_sync_actions(&entries, "left_to_right", "newest").unwrap();
        assert_eq!(actions.len(), 2);
        assert_eq!(actions[0].code, "COPY_LR");
        assert_eq!(actions[1].code, "UPDATE_R");
    }

    #[test]
    fn test_plan_sync_actions_bidirectional_newest() {
        let entries = vec![sync_test_entry(
            "c.txt",
            DiffStatus::Different,
            Some(30),
            Some(10),
        )];

        let actions = plan_sync_actions(&entries, "bidirectional", "newest").unwrap();
        assert_eq!(actions.len(), 1);
        assert_eq!(actions[0].code, "COPY_LR");
    }

    #[test]
    fn test_is_safe_relative_path() {
        assert!(is_safe_relative_path(Path::new("src/main.rs")));
        assert!(is_safe_relative_path(Path::new("./a/b.txt")));
        assert!(!is_safe_relative_path(Path::new("../secret")));
        assert!(!is_safe_relative_path(Path::new("/etc/passwd")));
    }

    fn diff_line(change_type: rcompare_core::text_diff::DiffChangeType) -> rcompare_core::text_diff::DiffLine {
        rcompare_core::text_diff::DiffLine {
            line_number_left: Some(1),
            line_number_right: Some(1),
            content: String::new(),
            change_type,
            highlighted_segments: Vec::new(),
        }
    }

    #[test]
    fn test_trim_diff_context_none_returns_all_lines() {
        use rcompare_core::text_diff::DiffChangeType;
        let lines = vec![diff_line(DiffChangeType::Equal), diff_line(DiffChangeType::Insert)];
        let trimmed = trim_diff_context(lines.clone(), None);
        assert_eq!(trimmed.len(), lines.len());
    }

    #[test]
    fn test_trim_diff_context_keeps_only_lines_near_changes() {
        use rcompare_core::text_diff::DiffChangeType;
        // 7 lines: Equal Equal Equal Insert Equal Equal Equal
        // context=1 should keep indices 2,3,4 (one before/after the change)
        let lines = vec![
            diff_line(DiffChangeType::Equal),
            diff_line(DiffChangeType::Equal),
            diff_line(DiffChangeType::Equal),
            diff_line(DiffChangeType::Insert),
            diff_line(DiffChangeType::Equal),
            diff_line(DiffChangeType::Equal),
            diff_line(DiffChangeType::Equal),
        ];
        let trimmed = trim_diff_context(lines, Some(1));
        assert_eq!(trimmed.len(), 3);
        assert_eq!(trimmed[0].change_type, DiffChangeType::Equal);
        assert_eq!(trimmed[1].change_type, DiffChangeType::Insert);
        assert_eq!(trimmed[2].change_type, DiffChangeType::Equal);
    }

    #[test]
    fn test_trim_diff_context_merges_overlapping_windows() {
        use rcompare_core::text_diff::DiffChangeType;
        // Two changes close together: their context windows overlap and
        // should merge into one contiguous kept region, not duplicate lines.
        let lines = vec![
            diff_line(DiffChangeType::Equal),
            diff_line(DiffChangeType::Delete),
            diff_line(DiffChangeType::Equal),
            diff_line(DiffChangeType::Insert),
            diff_line(DiffChangeType::Equal),
        ];
        let trimmed = trim_diff_context(lines, Some(1));
        assert_eq!(trimmed.len(), 5); // context=1 around both changes covers everything
    }

    #[test]
    fn test_trim_diff_context_empty_input() {
        let trimmed = trim_diff_context(Vec::new(), Some(2));
        assert!(trimmed.is_empty());
    }

    #[test]
    fn test_collect_copy_paths_merges_and_deduplicates() {
        let tmp_name = format!(
            "rcompare_copy_paths_{}_{}.txt",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        );
        let tmp_file = std::env::temp_dir().join(tmp_name);
        fs::write(&tmp_file, "# comment\nfoo.txt\nbar/baz.txt\nfoo.txt\n\n")
            .expect("write temp file");

        let cli_paths = vec!["foo.txt".to_string(), "abc.txt".to_string()];
        let paths = collect_copy_paths(&cli_paths, Some(&tmp_file)).expect("collect paths");

        assert_eq!(paths, vec!["abc.txt", "bar/baz.txt", "foo.txt"]);

        let _ = fs::remove_file(tmp_file);
    }

    #[test]
    fn test_resolve_diff_mode_auto_binary_fallback() {
        assert_eq!(
            resolve_diff_mode(Path::new("blob.bin"), "auto").unwrap(),
            "binary"
        );
    }

    #[test]
    fn test_resolve_diff_mode_auto_text_and_image() {
        assert_eq!(
            resolve_diff_mode(Path::new("src/main.rs"), "auto").unwrap(),
            "text"
        );
        assert_eq!(
            resolve_diff_mode(Path::new("assets/logo.png"), "auto").unwrap(),
            "image"
        );
    }

    #[test]
    fn test_build_binary_diff_result_ranges() {
        let left = b"abcXXXdefYYY";
        let right = b"abc123def000";
        let result = build_binary_diff_result(left, right, 10);
        assert!(!result.identical);
        assert_eq!(result.mismatch_bytes, 6);
        assert_eq!(result.mismatch_ranges.len(), 2);
        assert_eq!(result.mismatch_ranges[0].start, 3);
        assert_eq!(result.mismatch_ranges[0].end_exclusive, 6);
        assert_eq!(result.mismatch_ranges[1].start, 9);
        assert_eq!(result.mismatch_ranges[1].end_exclusive, 12);
    }

    #[test]
    fn test_build_binary_diff_result_truncation() {
        let left = b"abcdef";
        let right = b"aXcYef";
        let result = build_binary_diff_result(left, right, 1);
        assert!(!result.identical);
        assert!(result.truncated_ranges);
        assert_eq!(result.mismatch_ranges.len(), 1);
    }
}