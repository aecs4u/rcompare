//! Basic directory comparison example.
//!
//! This example demonstrates how to perform a simple directory comparison
//! using RCompare's core functionality.
//!
//! Usage:
//!   cargo run --example basic_comparison -- /path/to/left /path/to/right

use rcompare_common::{AppConfig, DiffStatus};
use rcompare_core::{ComparisonEngine, FolderScanner, HashCache};
use std::env;
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize logging
    tracing_subscriber::fmt::init();

    // Parse command line arguments
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        eprintln!("Usage: {} <left_dir> <right_dir>", args[0]);
        eprintln!("Example: {} /path/to/left /path/to/right", args[0]);
        std::process::exit(1);
    }

    let left_path = Path::new(&args[1]);
    let right_path = Path::new(&args[2]);

    // Verify directories exist
    if !left_path.exists() {
        eprintln!("Error: Left directory does not exist: {}", left_path.display());
        std::process::exit(1);
    }
    if !right_path.exists() {
        eprintln!("Error: Right directory does not exist: {}", right_path.display());
        std::process::exit(1);
    }

    println!("RCompare - Basic Directory Comparison");
    println!("======================================");
    println!("Left:  {}", left_path.display());
    println!("Right: {}", right_path.display());
    println!();

    // Create scanner with default configuration
    let config = AppConfig::default();
    let scanner = FolderScanner::new(config);

    // Scan both directories
    println!("Scanning directories...");
    let left_entries = scanner.scan(left_path)?;
    let right_entries = scanner.scan(right_path)?;
    println!("  Left:  {} entries", left_entries.len());
    println!("  Right: {} entries", right_entries.len());
    println!();

    // Create hash cache in temporary directory
    let cache_dir = std::env::temp_dir().join("rcompare_cache");
    let cache = HashCache::new(cache_dir)?;

    // Create comparison engine
    let engine = ComparisonEngine::new(cache);

    // Perform comparison
    println!("Comparing files...");
    let diffs = engine.compare(
        left_path,
        right_path,
        left_entries,
        right_entries,
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
                    // Skip identical files in detailed output
                }
            }
        }
    } else {
        println!("No differences found - directories are identical!");
    }

    // Persist cache for faster future comparisons
    engine.persist_cache()?;

    Ok(())
}
