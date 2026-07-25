//! Shared helpers used by more than one CLI command.
use rcompare_common::Vfs;
use rcompare_core::text_diff::{RegexRule, TextDiffConfig, WhitespaceMode};
use rcompare_core::vfs::{SevenZVfs, TarVfs, ZipVfs};
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};

pub(crate) enum ArchiveKind {
    Zip,
    Tar,
    SevenZ,
}

pub(crate) enum ScanSource {
    Local { root: PathBuf },
    Vfs { vfs: Box<dyn Vfs>, root: PathBuf },
}

impl ScanSource {
    pub(crate) fn root(&self) -> &std::path::Path {
        match self {
            Self::Local { root } | Self::Vfs { root, .. } => root.as_path(),
        }
    }

    pub(crate) fn vfs(&self) -> Option<&dyn Vfs> {
        match self {
            Self::Vfs { vfs, .. } => Some(vfs.as_ref()),
            Self::Local { .. } => None,
        }
    }
}
pub(crate) fn read_bytes_from_source_path(
    source_path: &Path,
    rel: &Path,
) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let source = build_scan_source(source_path)?;
    read_bytes_from_source(&source, rel)
}


pub(crate) fn read_bytes_from_source(
    source: &ScanSource,
    rel: &Path,
) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    match source {
        ScanSource::Local { root } => {
            let full = root.join(rel);
            if !full.exists() {
                return Err(format!("path not found: {}", full.display()).into());
            }
            if full.is_dir() {
                return Err(format!("path is a directory: {}", full.display()).into());
            }
            Ok(fs::read(&full)?)
        }
        ScanSource::Vfs { vfs, root } => {
            let full = if root.as_os_str().is_empty() {
                rel.to_path_buf()
            } else {
                root.join(rel)
            };
            let metadata = vfs
                .metadata(&full)
                .map_err(|e| format!("failed to stat {}: {}", full.display(), e))?;
            if metadata.is_dir {
                return Err(format!("path is a directory: {}", rel.display()).into());
            }
            let mut reader = vfs
                .open_file(&full)
                .map_err(|e| format!("failed to open {}: {}", full.display(), e))?;
            let mut bytes = Vec::new();
            reader.read_to_end(&mut bytes)?;
            Ok(bytes)
        }
    }
}


pub(crate) fn is_safe_relative_path(path: &Path) -> bool {
    if path.is_absolute() {
        return false;
    }
    for component in path.components() {
        match component {
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => return false,
            _ => {}
        }
    }
    true
}


pub(crate) fn apply_copy(source: &Path, target: &Path) -> Result<(), Box<dyn std::error::Error>> {
    if !source.exists() {
        return Err(format!("source does not exist: {}", source.display()).into());
    }
    if source.is_dir() {
        copy_dir_recursive(source, target)?;
        return Ok(());
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::copy(source, target)?;
    Ok(())
}


pub(crate) fn copy_dir_recursive(source: &Path, target: &Path) -> Result<(), Box<dyn std::error::Error>> {
    fs::create_dir_all(target)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let src = entry.path();
        let dst = target.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir_recursive(&src, &dst)?;
        } else {
            if let Some(parent) = dst.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(&src, &dst)?;
        }
    }
    Ok(())
}


pub(crate) fn apply_delete(target: &Path, delete_mode: &str) -> Result<(), Box<dyn std::error::Error>> {
    if !target.exists() {
        return Ok(());
    }
    if delete_mode == "trash" {
        move_to_local_trash(target)?;
        return Ok(());
    }
    if target.is_dir() {
        fs::remove_dir_all(target)?;
    } else {
        fs::remove_file(target)?;
    }
    Ok(())
}


pub(crate) fn move_to_local_trash(target: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let parent = target
        .parent()
        .ok_or_else(|| format!("cannot determine parent for {}", target.display()))?;
    let trash_dir = parent.join(".rcompare_trash");
    fs::create_dir_all(&trash_dir)?;

    let original_name = target
        .file_name()
        .ok_or_else(|| format!("invalid target name: {}", target.display()))?;
    let mut destination = trash_dir.join(original_name);
    if destination.exists() {
        let stem = target
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("item");
        let suffix = target
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| format!(".{e}"))
            .unwrap_or_default();
        let mut i = 1usize;
        loop {
            let candidate = trash_dir.join(format!("{stem}_{i}{suffix}"));
            if !candidate.exists() {
                destination = candidate;
                break;
            }
            i += 1;
        }
    }

    fs::rename(target, destination)?;
    Ok(())
}


/// Build TextDiffConfig from CLI flags
pub(crate) fn build_text_diff_config(
    ignore_whitespace: Option<String>,
    ignore_case: bool,
    regex_rules: Vec<String>,
) -> Result<TextDiffConfig, Box<dyn std::error::Error>> {
    let mut config = TextDiffConfig::new();

    // Parse whitespace mode
    if let Some(mode) = ignore_whitespace {
        config.whitespace_mode = match mode.to_lowercase().as_str() {
            "all" => WhitespaceMode::IgnoreAll,
            "leading" => WhitespaceMode::IgnoreLeading,
            "trailing" => WhitespaceMode::IgnoreTrailing,
            "changes" => WhitespaceMode::IgnoreChanges,
            _ => {
                return Err(format!(
                    "Invalid whitespace mode '{mode}'. Valid options: all, leading, trailing, changes"
                )
                .into())
            }
        };
    }

    // Set case sensitivity
    config.ignore_case = ignore_case;

    // Parse regex rules
    for rule_str in regex_rules {
        let parts: Vec<&str> = rule_str.splitn(3, ':').collect();
        if parts.len() < 2 {
            return Err(format!(
                "Invalid regex rule format '{rule_str}'. Expected 'pattern:replacement:description'"
            )
            .into());
        }

        let pattern = regex::Regex::new(parts[0])?;
        let replacement = parts[1].to_string();
        let description = parts.get(2).unwrap_or(&"").to_string();

        config.regex_rules.push(RegexRule {
            pattern,
            replacement,
            description,
        });
    }

    Ok(config)
}


/// Check if a file is likely a text file based on extension
pub(crate) fn is_text_file(path: &Path) -> bool {
    path.extension()
        .and_then(|ext| ext.to_str())
        .is_some_and(|ext| {
            matches!(
                ext.to_lowercase().as_str(),
                "txt"
                    | "md"
                    | "markdown"
                    | "rst"
                    | "log"
                    | "rs"
                    | "toml"
                    | "yaml"
                    | "yml"
                    | "json"
                    | "xml"
                    | "html"
                    | "htm"
                    | "css"
                    | "js"
                    | "ts"
                    | "tsx"
                    | "jsx"
                    | "c"
                    | "cpp"
                    | "cc"
                    | "cxx"
                    | "h"
                    | "hpp"
                    | "hxx"
                    | "cs"
                    | "java"
                    | "py"
                    | "rb"
                    | "go"
                    | "php"
                    | "pl"
                    | "sh"
                    | "bash"
                    | "zsh"
                    | "fish"
                    | "sql"
                    | "conf"
                    | "cfg"
                    | "ini"
                    | "properties"
                    | "cmake"
                    | "make"
                    | "dockerfile"
                    | "gitignore"
                    | "gitattributes"
            )
        })
}


pub(crate) fn build_scan_source(path: &std::path::Path) -> Result<ScanSource, Box<dyn std::error::Error>> {
    if path.is_dir() {
        return Ok(ScanSource::Local {
            root: path.to_path_buf(),
        });
    }

    if path.is_file() {
        return match detect_archive_kind(path) {
            Some(ArchiveKind::Zip) => Ok(ScanSource::Vfs {
                vfs: Box::new(ZipVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            Some(ArchiveKind::Tar) => Ok(ScanSource::Vfs {
                vfs: Box::new(TarVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            Some(ArchiveKind::SevenZ) => Ok(ScanSource::Vfs {
                vfs: Box::new(SevenZVfs::new(path.to_path_buf())?),
                root: PathBuf::new(),
            }),
            None => Err(format!(
                "Path is not a directory or supported archive (.zip, .tar, .tar.gz, .tgz, .7z): {}",
                path.display()
            )
            .into()),
        };
    }

    Err(format!("Path does not exist: {}", path.display()).into())
}


pub(crate) fn detect_archive_kind(path: &std::path::Path) -> Option<ArchiveKind> {
    let name = path.file_name()?.to_string_lossy().to_lowercase();
    if name.ends_with(".zip") {
        Some(ArchiveKind::Zip)
    } else if name.ends_with(".tar") || name.ends_with(".tar.gz") || name.ends_with(".tgz") {
        Some(ArchiveKind::Tar)
    } else if name.ends_with(".7z") {
        Some(ArchiveKind::SevenZ)
    } else {
        None
    }
}
