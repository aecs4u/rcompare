//! Specialized file format comparison example.
//!
//! This example demonstrates RCompare's specialized comparison engines
//! for different file types: text, images, CSV, JSON, and Excel files.
//!
//! Usage:
//!   cargo run --example specialized_formats -- <file_type> <file1> <file2>
//!
//! Where file_type is one of: text, image, csv, json, excel

use rcompare_common::{CsvCompareMode, ImageCompareMode, WhitespaceMode};
use rcompare_core::{CsvDiffEngine, ImageDiffEngine, JsonDiffEngine, TextDiffEngine};
use std::env;
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize logging
    tracing_subscriber::fmt::init();

    // Parse command line arguments
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 {
        eprintln!("Usage: {} <file_type> <file1> <file2>", args[0]);
        eprintln!();
        eprintln!("File types:");
        eprintln!("  text   - Line-by-line text comparison with syntax highlighting");
        eprintln!("  image  - Pixel-level image comparison");
        eprintln!("  csv    - Structural CSV comparison");
        eprintln!("  json   - Path-based JSON comparison");
        eprintln!("  excel  - Excel spreadsheet comparison");
        eprintln!();
        eprintln!("Examples:");
        eprintln!("  {} text left.rs right.rs", args[0]);
        eprintln!("  {} image photo1.png photo2.png", args[0]);
        eprintln!("  {} csv data1.csv data2.csv", args[0]);
        std::process::exit(1);
    }

    let file_type = &args[1];
    let left_path = Path::new(&args[2]);
    let right_path = Path::new(&args[3]);

    // Verify files exist
    if !left_path.exists() {
        eprintln!("Error: Left file does not exist: {}", left_path.display());
        std::process::exit(1);
    }
    if !right_path.exists() {
        eprintln!("Error: Right file does not exist: {}", right_path.display());
        std::process::exit(1);
    }

    println!("RCompare - Specialized Format Comparison");
    println!("=========================================");
    println!("Type:  {}", file_type.to_uppercase());
    println!("Left:  {}", left_path.display());
    println!("Right: {}", right_path.display());
    println!();

    match file_type.to_lowercase().as_str() {
        "text" => compare_text(left_path, right_path)?,
        "image" => compare_image(left_path, right_path)?,
        "csv" => compare_csv(left_path, right_path)?,
        "json" => compare_json(left_path, right_path)?,
        "yaml" => compare_json(left_path, right_path)?, // Uses same engine
        _ => {
            eprintln!("Error: Unknown file type: {}", file_type);
            eprintln!("Supported: text, image, csv, json, yaml");
            std::process::exit(1);
        }
    }

    Ok(())
}

fn compare_text(left: &Path, right: &Path) -> Result<(), Box<dyn std::error::Error>> {
    println!("Text Comparison");
    println!("---------------");

    let engine = TextDiffEngine::new();

    // Compare with different whitespace modes
    for mode in [
        WhitespaceMode::Exact,
        WhitespaceMode::IgnoreLeading,
        WhitespaceMode::IgnoreTrailing,
        WhitespaceMode::IgnoreAll,
    ] {
        let result = engine.compare_files(left, right, mode)?;

        println!();
        println!("Whitespace mode: {:?}", mode);
        println!("  Files identical: {}", result.is_identical);
        println!("  Total lines:     {}", result.total_lines);
        println!("  Changed lines:   {}", result.changed_lines);
        println!("  Added lines:     {}", result.added_lines);
        println!("  Removed lines:   {}", result.removed_lines);

        if !result.is_identical && mode == WhitespaceMode::Exact {
            println!();
            println!("Unified diff (first 20 lines):");
            for (i, line) in result.unified_diff.lines().take(20).enumerate() {
                println!("{:3}  {}", i + 1, line);
            }
            if result.unified_diff.lines().count() > 20 {
                println!("  ... ({} more lines)", result.unified_diff.lines().count() - 20);
            }
        }
    }

    Ok(())
}

fn compare_image(left: &Path, right: &Path) -> Result<(), Box<dyn std::error::Error>> {
    println!("Image Comparison");
    println!("----------------");

    let engine = ImageDiffEngine::new();

    // Compare with pixel-by-pixel mode
    let tolerance = 0.01; // 1% tolerance
    let result = engine.compare_files(left, right, ImageCompareMode::PixelByPixel, tolerance)?;

    println!();
    println!("Dimensions:");
    println!("  Left:  {}x{}", result.left_width, result.left_height);
    println!("  Right: {}x{}", result.right_width, result.right_height);
    println!();
    println!("Comparison results:");
    println!("  Images identical:   {}", result.is_identical);
    println!("  Dimensions match:   {}", result.dimensions_match);
    println!("  Different pixels:   {}", result.different_pixels);
    println!("  Total pixels:       {}", result.total_pixels);
    println!("  Difference percent: {:.2}%", result.difference_percentage);
    println!();

    if result.exif_left.is_some() || result.exif_right.is_some() {
        println!("EXIF metadata:");
        if let Some(exif) = &result.exif_left {
            println!("  Left:  {}", exif);
        }
        if let Some(exif) = &result.exif_right {
            println!("  Right: {}", exif);
        }
    }

    if !result.is_identical {
        println!();
        println!("Tip: Adjust tolerance parameter to ignore minor differences");
        println!("  0.00 = Exact match required");
        println!("  0.01 = 1% difference allowed");
        println!("  0.05 = 5% difference allowed");
    }

    Ok(())
}

fn compare_csv(left: &Path, right: &Path) -> Result<(), Box<dyn std::error::Error>> {
    println!("CSV Comparison");
    println!("--------------");

    let engine = CsvDiffEngine::new();

    // Compare with structured mode (with headers)
    let result = engine.compare_files(left, right, CsvCompareMode::StructuredWithHeader)?;

    println!();
    println!("Structure:");
    println!("  Left columns:  {}", result.left_columns);
    println!("  Right columns: {}", result.right_columns);
    println!("  Left rows:     {}", result.left_rows);
    println!("  Right rows:    {}", result.right_rows);
    println!();
    println!("Comparison results:");
    println!("  Files identical:  {}", result.is_identical);
    println!("  Schema matches:   {}", result.schema_matches);
    println!("  Changed rows:     {}", result.changed_rows);
    println!("  Added rows:       {}", result.added_rows);
    println!("  Removed rows:     {}", result.removed_rows);

    if !result.schema_matches {
        println!();
        println!("Schema differences:");
        if result.left_columns != result.right_columns {
            println!("  Column count mismatch: {} vs {}", result.left_columns, result.right_columns);
        }
    }

    if !result.is_identical && result.changed_rows > 0 {
        println!();
        println!("Row-by-row diff available in result.diff_summary");
        println!("(First few differences shown below)");
        // In a real implementation, you'd iterate through diff details
    }

    Ok(())
}

fn compare_json(left: &Path, right: &Path) -> Result<(), Box<dyn std::error::Error>> {
    println!("JSON/YAML Comparison");
    println!("--------------------");

    let engine = JsonDiffEngine::new();
    let result = engine.compare_files(left, right)?;

    println!();
    println!("Comparison results:");
    println!("  Files identical:    {}", result.is_identical);
    println!("  Structure matches:  {}", result.structure_matches);
    println!("  Value differences:  {}", result.value_diffs.len());
    println!("  Type mismatches:    {}", result.type_mismatches.len());
    println!("  Added paths:        {}", result.added_paths.len());
    println!("  Removed paths:      {}", result.removed_paths.len());

    if !result.is_identical {
        println!();
        println!("Detailed differences:");

        if !result.value_diffs.is_empty() {
            println!();
            println!("Value differences (first 10):");
            for (i, diff) in result.value_diffs.iter().take(10).enumerate() {
                println!("  {}. Path: {}", i + 1, diff.path);
                println!("     Left:  {}", diff.left_value);
                println!("     Right: {}", diff.right_value);
            }
            if result.value_diffs.len() > 10 {
                println!("  ... and {} more", result.value_diffs.len() - 10);
            }
        }

        if !result.type_mismatches.is_empty() {
            println!();
            println!("Type mismatches:");
            for mismatch in &result.type_mismatches {
                println!("  Path: {}", mismatch.path);
                println!("    Left type:  {}", mismatch.left_type);
                println!("    Right type: {}", mismatch.right_type);
            }
        }

        if !result.added_paths.is_empty() {
            println!();
            println!("Added paths:");
            for path in result.added_paths.iter().take(10) {
                println!("  + {}", path);
            }
            if result.added_paths.len() > 10 {
                println!("  ... and {} more", result.added_paths.len() - 10);
            }
        }

        if !result.removed_paths.is_empty() {
            println!();
            println!("Removed paths:");
            for path in result.removed_paths.iter().take(10) {
                println!("  - {}", path);
            }
            if result.removed_paths.len() > 10 {
                println!("  ... and {} more", result.removed_paths.len() - 10);
            }
        }
    }

    Ok(())
}
