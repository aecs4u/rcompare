//! `read` command: read one file from a side and export to stdout or a path.
use super::support::{is_safe_relative_path, read_bytes_from_source_path};
use std::fs;
use std::io::Write;
use std::path::PathBuf;

pub(crate) fn run_read(
    left: PathBuf,
    right: PathBuf,
    side: String,
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

    let side = side.to_lowercase();
    if !matches!(side.as_str(), "left" | "right") {
        return Err("invalid --side. Use: left, right".into());
    }

    let bytes = if side == "left" {
        read_bytes_from_source_path(&left, &rel)?
    } else {
        read_bytes_from_source_path(&right, &rel)?
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
