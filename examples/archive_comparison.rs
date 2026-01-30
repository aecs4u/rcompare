//! Archive comparison example.
//!
//! This example demonstrates how to compare files inside ZIP and TAR archives
//! without extracting them, using RCompare's VFS abstraction.
//!
//! Usage:
//!   cargo run --example archive_comparison -- archive1.zip archive2.zip

use rcompare_common::{AppConfig, DiffStatus};
use rcompare_core::vfs::{TarVfs, ZipVfs};
use rcompare_core::{ComparisonEngine, FolderScanner, HashCache};
use std::env;
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize logging
    tracing_subscriber::fmt::init();

    // Parse command line arguments
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        eprintln!("Usage: {} <archive1> <archive2>", args[0]);
        eprintln!("Supported formats: .zip, .tar, .tar.gz, .tgz");
        eprintln!("Example: {} backup1.zip backup2.zip", args[0]);
        std::process::exit(1);
    }

    let left_path = Path::new(&args[1]);
    let right_path = Path::new(&args[2]);

    // Verify files exist
    if !left_path.exists() {
        eprintln!("Error: Left archive does not exist: {}", left_path.display());
        std::process::exit(1);
    }
    if !right_path.exists() {
        eprintln!("Error: Right archive does not exist: {}", right_path.display());
        std::process::exit(1);
    }

    println!("RCompare - Archive Comparison");
    println!("==============================");
    println!("Left:  {}", left_path.display());
    println!("Right: {}", right_path.display());
    println!();

    // Detect archive type and create VFS instances
    let left_ext = left_path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    let right_ext = right_path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("");

    println!("Opening archives...");

    // Open left archive
    let left_vfs: Box<dyn rcompare_common::Vfs> = match left_ext {
        "zip" => Box::new(ZipVfs::new(left_path)?),
        "tar" | "gz" | "tgz" => Box::new(TarVfs::new(left_path)?),
        _ => {
            eprintln!("Error: Unsupported archive format: {}", left_ext);
            eprintln!("Supported: .zip, .tar, .tar.gz, .tgz");
            std::process::exit(1);
        }
    };

    // Open right archive
    let right_vfs: Box<dyn rcompare_common::Vfs> = match right_ext {
        "zip" => Box::new(ZipVfs::new(right_path)?),
        "tar" | "gz" | "tgz" => Box::new(TarVfs::new(right_path)?),
        _ => {
            eprintln!("Error: Unsupported archive format: {}", right_ext);
            std::process::exit(1);
        }
    };

    println!("  Left:  {} archive", left_ext.to_uppercase());
    println!("  Right: {} archive", right_ext.to_uppercase());
    println!();

    // Create scanner
    let config = AppConfig::default();
    let scanner = FolderScanner::new(config);

    // Scan both archives using VFS
    println!("Scanning archive contents...");
    let root = Path::new("/");
    let left_entries = scanner.scan_vfs(left_vfs.as_ref(), root)?;
    let right_entries = scanner.scan_vfs(right_vfs.as_ref(), root)?;
    println!("  Left:  {} entries", left_entries.len());
    println!("  Right: {} entries", right_entries.len());
    println!();

    // Create hash cache
    let cache_dir = std::env::temp_dir().join("rcompare_cache");
    let cache = HashCache::new(cache_dir)?;

    // Create comparison engine
    let engine = ComparisonEngine::new(cache);

    // Perform comparison with VFS
    println!("Comparing archive contents...");
    let diffs = engine.compare_with_vfs(
        root,
        root,
        left_entries,
        right_entries,
        Some(left_vfs.as_ref()),
        Some(right_vfs.as_ref()),
    )?;

    // Count results by status
    let mut identical = 0;
    let mut modified = 0;
    let mut left_only = 0;
    let mut right_only = 0;

    for diff in &diffs {
        match diff.status {
            DiffStatus::Identical => identical += 1,
            DiffStatus::Modified => modified += 1,
            DiffStatus::LeftOnly => left_only += 1,
            DiffStatus::RightOnly => right_only += 1,
        }
    }

    // Display summary
    println!();
    println!("Comparison Results:");
    println!("-------------------");
    println!("  Identical:  {}", identical);
    println!("  Modified:   {}", modified);
    println!("  Left only:  {}", left_only);
    println!("  Right only: {}", right_only);
    println!("  Total:      {}", diffs.len());
    println!();

    // Display differences in detail
    if modified > 0 || left_only > 0 || right_only > 0 {
        println!("Differences:");
        println!("------------");

        for diff in &diffs {
            match diff.status {
                DiffStatus::Modified => {
                    println!("  [MODIFIED] {}", diff.path.display());
                }
                DiffStatus::LeftOnly => {
                    println!("  [LEFT ONLY] {}", diff.path.display());
                }
                DiffStatus::RightOnly => {
                    println!("  [RIGHT ONLY] {}", diff.path.display());
                }
                DiffStatus::Identical => {
                    // Skip identical files
                }
            }
        }

        println!();
        println!("Tip: Use specialized diff modes for detailed comparison:");
        println!("  --text-diff    Line-by-line text comparison");
        println!("  --image-diff   Pixel-level image comparison");
        println!("  --csv-diff     Structural CSV comparison");
    } else {
        println!("No differences found - archives are identical!");
    }

    // Persist cache
    engine.persist_cache()?;

    Ok(())
}
