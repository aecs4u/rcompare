use thiserror::Error;

#[derive(Error, Debug)]
pub enum RCompareError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("VFS error: {0}")]
    Vfs(String),

    #[error("Path error: {0}")]
    Path(String),

    #[error("Invalid configuration: {0}")]
    Config(String),

    #[error("Hash cache error: {0}")]
    Cache(String),

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("Comparison error: {0}")]
    Comparison(String),
}

pub type Result<T> = std::result::Result<T, RCompareError>;

#[derive(Error, Debug)]
pub enum VfsError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Path not found: {0}")]
    NotFound(String),

    #[error("Permission denied: {0}")]
    PermissionDenied(String),

    #[error("Not a directory: {0}")]
    NotADirectory(String),

    #[error("Not a file: {0}")]
    NotAFile(String),

    #[error("Unsupported operation: {0}")]
    Unsupported(String),
}
