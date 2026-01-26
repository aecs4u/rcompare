use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::SystemTime;
use uuid::Uuid;

/// Represents a file or directory entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    pub path: PathBuf,
    pub size: u64,
    pub modified: SystemTime,
    pub is_dir: bool,
}

/// Metadata for a file or directory
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMetadata {
    pub size: u64,
    pub modified: SystemTime,
    pub is_dir: bool,
    pub is_symlink: bool,
}

/// Status of a file comparison
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DiffStatus {
    /// Files are identical
    Same,
    /// Files differ in content
    Different,
    /// File exists only on the left side
    OrphanLeft,
    /// File exists only on the right side
    OrphanRight,
    /// Files have the same size but haven't been fully compared yet
    Unchecked,
}

/// Represents a node in the diff tree, aligning files from left and right
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffNode {
    pub relative_path: PathBuf,
    pub left: Option<FileEntry>,
    pub right: Option<FileEntry>,
    pub status: DiffStatus,
}

/// Status of a three-way file comparison
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ThreeWayDiffStatus {
    /// All three versions are identical
    AllSame,
    /// Left differs from base (right same as base)
    LeftChanged,
    /// Right differs from base (left same as base)
    RightChanged,
    /// Both left and right differ from base (potential conflict)
    BothChanged,
    /// File exists only in base
    BaseOnly,
    /// File exists only in left
    LeftOnly,
    /// File exists only in right
    RightOnly,
    /// File exists in left and right but not base (both added)
    BothAdded,
    /// File exists in base and left only
    BaseAndLeft,
    /// File exists in base and right only
    BaseAndRight,
}

/// Represents a node in a three-way diff tree
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreeWayDiffNode {
    pub relative_path: PathBuf,
    pub base: Option<FileEntry>,
    pub left: Option<FileEntry>,
    pub right: Option<FileEntry>,
    pub status: ThreeWayDiffStatus,
}

/// Hash result for a file
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileHash {
    pub full_hash: Option<String>,
    pub partial_hash: Option<String>,
}

/// Cache key for file hashing
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct CacheKey {
    pub path: PathBuf,
    pub modified: SystemTime,
    pub size: u64,
}

/// A saved session profile for quick-loading comparisons
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionProfile {
    /// Profile name
    pub name: String,
    /// Left path for comparison
    pub left_path: PathBuf,
    /// Right path for comparison
    pub right_path: PathBuf,
    /// Custom ignore patterns for this profile
    pub ignore_patterns: Vec<String>,
    /// Last time this profile was used (Unix timestamp)
    pub last_used: u64,
}

/// Application configuration
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AppConfig {
    /// Ignore patterns (e.g., "*.o", "node_modules/")
    #[serde(default)]
    pub ignore_patterns: Vec<String>,

    /// Whether to follow symbolic links
    #[serde(default)]
    pub follow_symlinks: bool,

    /// Whether to use hash verification
    #[serde(default)]
    pub use_hash_verification: bool,

    /// Cache directory
    #[serde(default)]
    pub cache_dir: Option<PathBuf>,

    /// Enable portable mode (config alongside binary)
    #[serde(default)]
    pub portable_mode: bool,

    /// Saved session profiles
    #[serde(default)]
    pub profiles: Vec<SessionProfile>,
}

/// Session identifier for a comparison
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SessionId(pub Uuid);

impl SessionId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl Default for SessionId {
    fn default() -> Self {
        Self::new()
    }
}

/// BLAKE3 hash value (32 bytes)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Blake3Hash(pub [u8; 32]);

impl Blake3Hash {
    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }

    pub fn to_hex(&self) -> String {
        hex::encode(self.0)
    }
}

impl From<blake3::Hash> for Blake3Hash {
    fn from(hash: blake3::Hash) -> Self {
        Self(*hash.as_bytes())
    }
}
