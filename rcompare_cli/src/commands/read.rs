//! `read` command: read one file from a side and export to stdout or a path.
use super::support::{copy_source_file_to_writer, is_safe_relative_path, Side};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use tempfile::NamedTempFile;

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

    let source = match side {
        Side::Left => left,
        Side::Right => right,
    };
    if let Some(out_path) = out {
        let parent = out_path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
            .unwrap_or_else(|| Path::new("."));
        fs::create_dir_all(parent)?;
        let mut output = NamedTempFile::new_in(parent)?;
        let bytes_written = copy_source_file_to_writer(&source, &rel, &mut output)?;
        output.flush()?;
        output.persist(&out_path)?;
        println!("Wrote {} bytes to {}", bytes_written, out_path.display());
    } else {
        let mut stdout = std::io::stdout();
        copy_source_file_to_writer(&source, &rel, &mut stdout)?;
        stdout.flush()?;
    }

    Ok(())
}
