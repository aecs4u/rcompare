//! Shared helpers used by more than one CLI command.
use rcompare_common::{default_cache_dir, load_config, DiffNode, Vfs};
use rcompare_core::text_diff::{RegexRule, TextDiffConfig, WhitespaceMode};
use rcompare_core::vfs::{SevenZVfs, TarVfs, ZipVfs};
use rcompare_core::{CacheMode, ComparisonEngine, FolderScanner, HashCache};
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

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

/// Output-shaping flags for the `scan` command: how to format JSON, whether
/// to cap/omit entries, and where to write the result. Bundled into one
/// struct instead of four more positional params on an already-long
/// `run_scan` signature.
#[derive(Default)]
pub(crate) struct OutputOptions {
    pub(crate) pretty: bool,
    pub(crate) jsonl: bool,
    pub(crate) summary_only: bool,
    pub(crate) max_results: Option<usize>,
    pub(crate) output: Option<PathBuf>,
    /// Trim embedded text-diff JSON output to N lines of context around each
    /// change (unified-diff style) instead of embedding every equal line.
    pub(crate) context: Option<usize>,
}

/// Trim a text diff's lines to `context` lines of surrounding equal-content
/// around each change (unified-diff style), dropping everything else.
/// `None` returns `lines` unchanged. Only affects the embedded JSON output --
/// the human-readable path only ever printed summary counts, never the lines
/// themselves.
pub(crate) fn trim_diff_context(
    lines: Vec<rcompare_core::text_diff::DiffLine>,
    context: Option<usize>,
) -> Vec<rcompare_core::text_diff::DiffLine> {
    use rcompare_core::text_diff::DiffChangeType;

    let Some(context) = context else {
        return lines;
    };
    if lines.is_empty() {
        return lines;
    }

    let mut keep = vec![false; lines.len()];
    for (i, line) in lines.iter().enumerate() {
        if line.change_type != DiffChangeType::Equal {
            let start = i.saturating_sub(context);
            let end = (i + context + 1).min(lines.len());
            keep[start..end].fill(true);
        }
    }

    lines
        .into_iter()
        .zip(keep)
        .filter_map(|(line, k)| k.then_some(line))
        .collect()
}

/// Options for [`run_core_scan`], the in-process scan+compare service shared
/// by `scan` and `sync` (the latter used to shell out to a second copy of
/// this binary and parse its JSON output; it now calls this directly).
pub(crate) struct CoreScanOptions {
    pub(crate) left: PathBuf,
    pub(crate) right: PathBuf,
    pub(crate) ignore_patterns: Vec<String>,
    pub(crate) follow_symlinks: bool,
    pub(crate) verify_hashes: bool,
    pub(crate) no_verify_hashes: bool,
    pub(crate) cache_dir: Option<PathBuf>,
    pub(crate) strict: bool,
    pub(crate) no_cache: bool,
    pub(crate) cache_read_only: bool,
    pub(crate) hash_jobs: Option<usize>,
}

/// Result of [`run_core_scan`]: the comparison's diff nodes plus any
/// non-fatal scan warnings (races, permission errors -- see
/// `FolderScanner`'s race tolerance), with the hash cache already persisted.
pub(crate) struct CoreScanResult {
    pub(crate) diff_nodes: Vec<DiffNode>,
    pub(crate) warnings: Vec<String>,
}

/// Scan both sides and compare them in-process: no subprocess, no JSON
/// round-trip. Used directly by `sync` (which has no need for `scan`'s
/// progress bars / specialized-diff output) and could equally back `scan`
/// itself for the common case.
pub(crate) fn run_core_scan(
    opts: &CoreScanOptions,
    stop_flag: &Arc<AtomicBool>,
) -> Result<CoreScanResult, Box<dyn std::error::Error>> {
    if !opts.left.exists() {
        return Err(format!("Left path does not exist: {}", opts.left.display()).into());
    }
    if !opts.right.exists() {
        return Err(format!("Right path does not exist: {}", opts.right.display()).into());
    }

    let loaded = load_config(false)?;
    let mut config = loaded.config;

    if !opts.ignore_patterns.is_empty() {
        config.ignore_patterns.extend(opts.ignore_patterns.clone());
    }
    if opts.follow_symlinks {
        config.follow_symlinks = true;
    }
    let mut verify_hashes = if opts.verify_hashes {
        true
    } else if opts.no_verify_hashes {
        false
    } else {
        config.use_hash_verification
    };
    config.use_hash_verification = verify_hashes;
    if let Some(cache_dir) = opts.cache_dir.clone() {
        config.cache_dir = Some(cache_dir);
    }

    let hash_cache = if opts.no_cache {
        HashCache::disabled()
    } else {
        let cache_path = match config.cache_dir.clone() {
            Some(path) => path,
            None => default_cache_dir(loaded.portable, &loaded.path)?,
        };
        let mode = if opts.cache_read_only {
            CacheMode::ReadOnly
        } else {
            CacheMode::ReadWrite
        };
        HashCache::with_mode(cache_path, mode)?
    };

    let left_scanner = FolderScanner::new(config.clone()).with_strict(opts.strict);
    let right_scanner = FolderScanner::new(config).with_strict(opts.strict);

    let left_source = build_scan_source(&opts.left)?;
    let right_source = build_scan_source(&opts.right)?;

    let has_archive =
        matches!(left_source, ScanSource::Vfs { .. }) || matches!(right_source, ScanSource::Vfs { .. });
    if has_archive && !opts.no_verify_hashes {
        verify_hashes = true;
    }

    let mut warnings = Vec::new();

    let left_outcome = match &left_source {
        ScanSource::Local { root } => left_scanner.scan_with_cancel(root, Some(stop_flag.as_ref())),
        ScanSource::Vfs { vfs, root } => {
            left_scanner.scan_vfs_with_cancel(vfs.as_ref(), root, Some(stop_flag.as_ref()))
        }
    }?;
    let right_outcome = match &right_source {
        ScanSource::Local { root } => right_scanner.scan_with_cancel(root, Some(stop_flag.as_ref())),
        ScanSource::Vfs { vfs, root } => {
            right_scanner.scan_vfs_with_cancel(vfs.as_ref(), root, Some(stop_flag.as_ref()))
        }
    }?;

    warnings.extend(
        left_outcome
            .warnings
            .into_iter()
            .map(|w| format!("{}: {}", w.path.display(), w.message)),
    );
    warnings.extend(
        right_outcome
            .warnings
            .into_iter()
            .map(|w| format!("{}: {}", w.path.display(), w.message)),
    );

    let comparison_engine = ComparisonEngine::new(hash_cache)
        .with_hash_verification(verify_hashes)
        .with_hash_concurrency(opts.hash_jobs);

    let diff_nodes = comparison_engine.compare_with_vfs_and_cancel(
        left_source.root(),
        right_source.root(),
        left_outcome.entries,
        right_outcome.entries,
        left_source.vfs(),
        right_source.vfs(),
        Some(stop_flag.as_ref()),
    )?;

    comparison_engine.persist_cache()?;

    Ok(CoreScanResult {
        diff_nodes,
        warnings,
    })
}
