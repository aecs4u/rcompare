pub mod vfs;
pub mod hash_cache;
pub mod scanner;
pub mod comparison;
pub mod text_diff;
pub mod file_operations;
pub mod binary_diff;
pub mod image_diff;

pub use vfs::LocalVfs;
pub use hash_cache::HashCache;
pub use scanner::FolderScanner;
pub use comparison::ComparisonEngine;
pub use text_diff::TextDiffEngine;
pub use file_operations::FileOperations;
pub use binary_diff::BinaryDiffEngine;
pub use image_diff::{ImageDiffEngine, ImageDiffResult, ImageCompareMode, is_image_file};
