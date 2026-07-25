//! `read` command: read one file from a side and export to stdout or a path.
use super::support::{is_safe_relative_path, read_bytes_from_source_path, Side};
use std::fs;
use std::io::Write;
use std::path::PathBuf;

pub(crate) fn run_read(
    left: PathBuf,
    right: PathBuf,
    side: Side,
    rel_path: String,
    out: Option<PathBuf>,
) -> Result<(), Box<dyn std::error::Error>> {
    let rel = PathBuf::from(rel_path.trim());
    if rel.as_os_str().is_empty() {
        return Err("--path cannot be empty".into());
    }
    if !is_safe_relative_path(&rel) {
        return Err("--path must be a safe relative path".into());
    }

    let bytes = match side {
        Side::Left => read_bytes_from_source_path(&left, &rel)?,
        Side::Right => read_bytes_from_source_path(&right, &rel)?,
    };

    if let Some(out_path) = out {
        if let Some(parent) = out_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&out_path, &bytes)?;
        println!("Wrote {} bytes to {}", bytes.len(), out_path.display());
    } else {
        let mut stdout = std::io::stdout();
        stdout.write_all(&bytes)?;
        stdout.flush()?;
    }

    Ok(())
}
