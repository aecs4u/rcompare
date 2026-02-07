//! Core business logic for RCompare file and directory comparison.
//!
//! This crate provides the foundational comparison engine, specialized file diff
//! algorithms, VFS abstraction for archives/cloud storage, and patch parsing/generation
//! capabilities. It is UI-agnostic and can be used by CLI, GUI, or other frontends.
//!
//! # Architecture
//!
//! RCompare follows the Czkawka architectural pattern with strict separation between
//! core logic and presentation layers. This crate (`rcompare_core`) contains:
//!
//! - **File tree comparison**: [`ComparisonEngine`] for two-way and three-way diffs
//! - **Directory scanning**: [`FolderScanner`] with gitignore support
//! - **Hash caching**: [`HashCache`] for persistent BLAKE3 hashes
//! - **Specialized comparisons**: Text, binary, image, CSV, JSON, Excel, Parquet
//! - **VFS abstraction**: Support for archives (ZIP, TAR, 7Z) and cloud storage (S3, SSH)
//! - **Patch operations**: Parsing, applying, and serializing unified/context diffs
//!
//! # Quick Start
//!
//! Basic directory comparison:
//!
//! ```no_run
//! use rcompare_core::{FolderScanner, ComparisonEngine, HashCache};
//! use rcompare_common::AppConfig;
//! use std::path::Path;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! // Create scanner and cache
//! let scanner = FolderScanner::new(AppConfig::default());
//! let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
//!
//! // Scan directories
//! let left = scanner.scan(Path::new("/left"))?;
//! let right = scanner.scan(Path::new("/right"))?;
//!
//! // Compare
//! let engine = ComparisonEngine::new(cache);
//! let diffs = engine.compare(
//!     Path::new("/left"),
//!     Path::new("/right"),
//!     left,
//!     right,
//! )?;
//!
//! // Process results
//! for diff in &diffs {
//!     println!("{:?}: {}", diff.status, diff.relative_path.display());
//! }
//! # Ok(())
//! # }
//! ```
//!
//! # Specialized File Comparisons
//!
//! RCompare provides specialized diff engines for various file types:
//!
//! ```no_run
//! use rcompare_core::TextDiffEngine;
//! use rcompare_core::text_diff::{TextDiffConfig, WhitespaceMode};
//! use std::path::Path;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! // Text comparison with syntax highlighting
//! let config = TextDiffConfig {
//!     whitespace_mode: WhitespaceMode::IgnoreAll,
//!     ..Default::default()
//! };
//! let text_engine = TextDiffEngine::with_config(config);
//! let text_diff = text_engine.compare_files(
//!     Path::new("left.rs"),
//!     Path::new("right.rs"),
//! )?;
//! # Ok(())
//! # }
//! ```
//!
//! # VFS Support
//!
//! Compare files inside archives without extraction:
//!
//! ```no_run
//! use rcompare_core::{FolderScanner, ComparisonEngine};
//! use rcompare_core::vfs::ZipVfs;
//! use rcompare_core::HashCache;
//! use rcompare_common::{AppConfig, Vfs};
//! use std::path::Path;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let scanner = FolderScanner::new(AppConfig::default());
//! let cache = HashCache::new(Path::new(".cache").to_path_buf())?;
//! let engine = ComparisonEngine::new(cache);
//!
//! // Compare ZIP archives
//! let left_zip = ZipVfs::new(Path::new("left.zip").to_path_buf())?;
//! let right_zip = ZipVfs::new(Path::new("right.zip").to_path_buf())?;
//!
//! let left_entries = scanner.scan_vfs(&left_zip, Path::new("/"))?;
//! let right_entries = scanner.scan_vfs(&right_zip, Path::new("/"))?;
//!
//! let diffs = engine.compare_with_vfs(
//!     Path::new("/"),
//!     Path::new("/"),
//!     left_entries,
//!     right_entries,
//!     Some(&left_zip as &dyn Vfs),
//!     Some(&right_zip as &dyn Vfs),
//! )?;
//! # Ok(())
//! # }
//! ```
//!
//! # Feature Flags
//!
//! This crate supports optional features to reduce binary size and compile times:
//!
//! - **`default`**: Enables `cloud`, `archives`, and `specialized` features
//! - **`cloud`**: Cloud storage support (S3, SSH/SFTP, WebDAV)
//! - **`archives`**: Archive format support (ZIP, TAR, 7Z, RAR)
//! - **`specialized`**: All specialized file format comparisons (enables all `*-diff` features)
//! - **`csv-diff`**: CSV file comparison
//! - **`excel-diff`**: Excel workbook comparison
//! - **`json-diff`**: JSON/YAML structural comparison
//! - **`parquet-diff`**: Parquet DataFrame comparison
//! - **`image-diff`**: Image pixel-level comparison with EXIF
//!
//! ## Example
//!
//! To build with minimal features:
//!
//! ```toml
//! [dependencies]
//! rcompare_core = { version = "0.1", default-features = false }
//! ```
//!
//! To enable specific features:
//!
//! ```toml
//! [dependencies]
//! rcompare_core = { version = "0.1", default-features = false, features = ["archives", "csv-diff"] }
//! ```

// Core modules (always available)
pub mod binary_diff;
pub mod comparison;
pub mod file_operations;
pub mod hash_cache;
pub mod merge_engine;
pub mod patch_engine;
pub mod patch_parser;
pub mod patch_serializer;
pub mod resumable_copy;
pub mod scanner;
pub mod text_diff;
pub mod vfs;

// Specialized comparison modules (feature-gated)
#[cfg(feature = "csv-diff")]
pub mod csv_diff;

#[cfg(feature = "excel-diff")]
pub mod excel_diff;

#[cfg(feature = "image-diff")]
pub mod image_diff;

#[cfg(feature = "json-diff")]
pub mod json_diff;

#[cfg(feature = "parquet-diff")]
pub mod parquet_diff;

// Core exports (always available)
pub use binary_diff::BinaryDiffEngine;
pub use comparison::ComparisonEngine;
pub use file_operations::FileOperations;
pub use hash_cache::HashCache;
pub use merge_engine::MergeEngine;
pub use patch_engine::PatchEngine;
pub use patch_parser::PatchParser;
pub use patch_serializer::PatchSerializer;
pub use resumable_copy::{CopyCheckpoint, ResumableCopy, ResumableResult};
pub use scanner::FolderScanner;
pub use text_diff::TextDiffEngine;
pub use vfs::LocalVfs;

// Feature-gated exports
#[cfg(feature = "csv-diff")]
pub use csv_diff::{is_csv_file, CsvCompareMode, CsvDiffEngine, CsvDiffResult};

#[cfg(feature = "excel-diff")]
pub use excel_diff::{is_excel_file, ExcelDiffEngine, ExcelDiffResult};

#[cfg(feature = "image-diff")]
pub use image_diff::{is_image_file, ImageCompareMode, ImageDiffEngine, ImageDiffResult};

#[cfg(feature = "json-diff")]
pub use json_diff::{is_json_file, is_yaml_file, JsonDiffEngine, JsonDiffResult};

#[cfg(feature = "parquet-diff")]
pub use parquet_diff::{is_parquet_file, ParquetDiffEngine, ParquetDiffResult};
