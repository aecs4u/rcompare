use clap::{Parser, Subcommand};
use rcompare_common::{DiffStatus, Vfs, default_cache_dir, load_config};
use serde::Serialize;
use rcompare_core::{ComparisonEngine, FolderScanner, HashCache};
use rcompare_core::vfs::{SevenZVfs, TarVfs, ZipVfs};
use std::io::IsTerminal;
use std::path::PathBuf;
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

        /// Output results as JSON
        #[arg(long)]
        json: bool,

        /// Disable ANSI colors in output
        #[arg(long)]
        no_color: bool,

        /// Use columned diff-style output (side-by-side comparison)
        #[arg(short = 'c', long)]
        columns: bool,
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
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info"))
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
            json,
            no_color,
            columns,
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
                json,
                no_color,
                columns,
            ) {
                error!("Scan failed: {}", e);
                std::process::exit(1);
            }
        }
    }
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
    json: bool,
    no_color: bool,
    columns: bool,
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

    info!("Scanning left source...");
    let left_entries = scan_source(&left_scanner, &left_source)?;
    info!("Found {} entries in left source", left_entries.len());

    info!("Scanning right source...");
    let right_entries = scan_source(&right_scanner, &right_source)?;
    info!("Found {} entries in right source", right_entries.len());

    // Compare directories
    info!("Comparing directories...");
    let comparison_engine = ComparisonEngine::new(hash_cache)
        .with_hash_verification(verify_hashes);
    let diff_nodes = comparison_engine.compare_with_vfs(
        left_source.root(),
        right_source.root(),
        left_entries,
        right_entries,
        left_source.vfs(),
        right_source.vfs(),
    )?;
    comparison_engine.persist_cache()?;

    if json {
        let report = build_json_report(
            &left,
            &right,
            &diff_nodes,
            diff_only,
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

            // Skip identical files if diff_only is set
            if diff_only && node.status == DiffStatus::Same {
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
                (match node.status {
                    DiffStatus::Same => "\x1b[32m",        // Green
                    DiffStatus::Different => "\x1b[31m",   // Red
                    DiffStatus::OrphanLeft => "\x1b[33m",  // Yellow
                    DiffStatus::OrphanRight => "\x1b[34m", // Blue
                    DiffStatus::Unchecked => "\x1b[36m",   // Cyan
                }, "\x1b[0m")
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

            // Skip identical files if diff_only is set
            if diff_only && node.status == DiffStatus::Same {
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
                (match node.status {
                    DiffStatus::Same => "\x1b[32m",        // Green
                    DiffStatus::Different => "\x1b[31m",   // Red
                    DiffStatus::OrphanLeft => "\x1b[33m",  // Yellow
                    DiffStatus::OrphanRight => "\x1b[34m", // Blue
                    DiffStatus::Unchecked => "\x1b[36m",   // Cyan
                }, "\x1b[0m")
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
    let same_mark = if use_color { "\x1b[32m(==)\x1b[0m" } else { "(==)" };
    let diff_mark = if use_color { "\x1b[31m(!=)\x1b[0m" } else { "(!=)" };
    let left_mark = if use_color { "\x1b[33m(<<)\x1b[0m" } else { "(<<)" };
    let right_mark = if use_color { "\x1b[34m(>>)\x1b[0m" } else { "(>>)" };
    let unchecked_mark = if use_color { "\x1b[36m(??)\x1b[0m" } else { "(??)" };

    println!("Summary:");
    println!("  Total entries:   {}", diff_nodes.len());
    println!("  Identical:       {} {}", same_count, same_mark);
    println!("  Different:       {} {}", different_count, diff_mark);
    println!("  Left only:       {} {}", orphan_left_count, left_mark);
    println!("  Right only:      {} {}", orphan_right_count, right_mark);
    println!("  Unchecked:       {} {}", unchecked_count, unchecked_mark);
    println!("{}", "=".repeat(80));

    Ok(())
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
    left: &PathBuf,
    right: &PathBuf,
    diff_nodes: &[rcompare_common::DiffNode],
    diff_only: bool,
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

        if diff_only && node.status == DiffStatus::Same {
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
            ).into()),
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

        let report = build_json_report(&left, &right, &diff_nodes, false);

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

        let report = build_json_report(&left, &right, &diff_nodes, true);

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
