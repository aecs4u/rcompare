//! Shared helpers used by more than one CLI command.
use clap::ValueEnum;
use rcompare_common::{default_cache_dir, load_config, DiffNode, Vfs};
use rcompare_core::text_diff::{RegexRule, TextDiffConfig, WhitespaceMode};
use rcompare_core::vfs::LocalVfs;
use rcompare_core::vfs::{FilteredVfs, UnionVfs};
#[cfg(feature = "cloud")]
use rcompare_core::vfs::{
    S3Auth, S3Config, S3Vfs, SftpAuth, SftpConfig, SftpVfs, WebDavAuth, WebDavConfig, WebDavVfs,
};
#[cfg(feature = "archives")]
use rcompare_core::vfs::{
    SevenZVfs, TarVfs, Writable7zVfs, WritableTarVfs, WritableZipVfs, ZipVfs,
};
use rcompare_core::{CacheMode, ComparisonEngine, FolderScanner, HashCache, ResumableCopy};
use serde_json::{json, Value};
use std::fs;
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

#[cfg(feature = "cloud")]
pub(crate) const REMOTE_SOURCE_SCHEMES: &[&str] = &["s3", "sftp", "dav", "davs"];

pub(crate) const JSON_SCHEMA_V2_VERSION: &str = "2.0.0";

/// Build the common v2 machine-readable result envelope.
pub(crate) fn json_v2_envelope(
    command: &str,
    status: &str,
    summary: Value,
    data: Value,
    warnings: Vec<String>,
) -> Value {
    json!({
        "schema_version": JSON_SCHEMA_V2_VERSION,
        "command": command,
        "status": status,
        "summary": summary,
        "data": data,
        "warnings": warnings,
    })
}

/// Move the common fields from a v1 report to the v2 envelope and leave the
/// command-specific fields in `data`.
pub(crate) fn envelope_from_v1_report(command: &str, status: &str, mut report: Value) -> Value {
    let Some(fields) = report.as_object_mut() else {
        return json_v2_envelope(command, status, json!({}), report, Vec::new());
    };
    fields.remove("schema_version");
    let summary = fields.remove("summary").unwrap_or_else(|| json!({}));
    let warnings = fields
        .remove("warnings")
        .and_then(|value| value.as_array().cloned())
        .unwrap_or_default()
        .into_iter()
        .filter_map(|value| value.as_str().map(str::to_string))
        .collect();
    json_v2_envelope(command, status, summary, report, warnings)
}

#[cfg(feature = "cloud")]
fn validate_cloud_url(parsed: &url::Url) -> Result<(), Box<dyn std::error::Error>> {
    if !REMOTE_SOURCE_SCHEMES.contains(&parsed.scheme()) {
        return Err(format!("unsupported endpoint scheme '{}'", parsed.scheme()).into());
    }
    if !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.query().is_some()
        || parsed.fragment().is_some()
    {
        return Err(
            "remote credentials and tokens must be supplied through the configured credential provider or environment, not embedded in the URL".into(),
        );
    }
    Ok(())
}

/// Direction for the `sync` command. Parsed and validated by clap itself
/// (invalid values are rejected with a generated "possible values" error),
/// so command code never re-validates these as strings.
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum SyncDirection {
    LeftToRight,
    RightToLeft,
    Bidirectional,
    UpdateLeft,
    UpdateRight,
    UpdateBoth,
    MirrorLeft,
    MirrorRight,
}

impl SyncDirection {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::LeftToRight => "left_to_right",
            Self::RightToLeft => "right_to_left",
            Self::Bidirectional => "bidirectional",
            Self::UpdateLeft => "update_left",
            Self::UpdateRight => "update_right",
            Self::UpdateBoth => "update_both",
            Self::MirrorLeft => "mirror_left",
            Self::MirrorRight => "mirror_right",
        }
    }
}

/// Direction for the `copy` command (no bidirectional mode, unlike `sync`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum CopyDirection {
    LeftToRight,
    RightToLeft,
}

impl CopyDirection {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::LeftToRight => "left_to_right",
            Self::RightToLeft => "right_to_left",
        }
    }
}

/// How `sync` deletes files that no longer exist on the source side.
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum DeleteMode {
    Trash,
    Permanent,
}

/// Conflict resolution policy for bidirectional `sync`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum ConflictPolicy {
    Newest,
    Left,
    Right,
    Skip,
    Error,
}

impl ConflictPolicy {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Newest => "newest",
            Self::Left => "left",
            Self::Right => "right",
            Self::Skip => "skip",
            Self::Error => "error",
        }
    }
}

/// Which source side `read` reads from.
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum Side {
    Left,
    Right,
}

/// Requested diff mode for `diff-file` and `scan`'s per-format flags, as
/// typed by the user (`Auto` is resolved away by [`resolve_diff_mode`]
/// before any comparison engine runs).
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum DiffModeArg {
    Auto,
    Text,
    Binary,
    Image,
    Csv,
    Excel,
    Json,
    Yaml,
    Parquet,
}

/// A concrete (non-`Auto`) diff mode, produced by [`resolve_diff_mode`].
/// Splitting this out from [`DiffModeArg`] lets the dispatch `match` in
/// `run_diff_file` be exhaustive without an `Auto` arm that can never fire.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ResolvedDiffMode {
    Text,
    Binary,
    Image,
    Csv,
    Excel,
    Json,
    Yaml,
    Parquet,
}

impl ResolvedDiffMode {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Text => "text",
            Self::Binary => "binary",
            Self::Image => "image",
            Self::Csv => "csv",
            Self::Excel => "excel",
            Self::Json => "json",
            Self::Yaml => "yaml",
            Self::Parquet => "parquet",
        }
    }
}

/// Explicit progress-reporting policy for `scan` (`--progress`), decoupled
/// from `--json`/`--jsonl`. Previously JSON progress events on stderr were
/// implicitly tied to `--json` with no way to opt in/out independently;
/// `Auto` reproduces that historical behavior exactly (needed for backward
/// compatibility — teczka's `comparison_worker.py` parses this stderr
/// stream), while `Never`/`Json` make the choice explicit.
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum ProgressPolicy {
    /// Human progress bar when stderr is a terminal and output isn't JSON;
    /// structured JSON progress events on stderr when `--json`/`--jsonl` is
    /// set. Matches the tool's historical implicit behavior.
    Auto,
    /// No progress output at all (human bar or JSON events), regardless of
    /// `--json` or terminal detection.
    Never,
    /// Always emit structured JSON progress events on stderr, even with
    /// human-readable stdout output.
    Json,
}

/// Whitespace-handling mode for text comparison (`--ignore-whitespace`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "snake_case")]
pub(crate) enum WhitespaceModeArg {
    All,
    Leading,
    Trailing,
    Changes,
}

#[cfg(feature = "archives")]
pub(crate) enum ArchiveKind {
    Zip,
    Tar,
    SevenZ,
}

#[allow(dead_code)] // VFS variant is unavailable in minimal builds.
pub(crate) enum ScanSource {
    Local { root: PathBuf },
    Vfs { vfs: Box<dyn Vfs>, root: PathBuf },
}

/// A resolved mutation endpoint. The endpoint always exposes paths relative
/// to its configured root; this keeps local, archive, and remote operations
/// on the same path contract.
pub(crate) struct MutationEndpoint {
    pub(crate) vfs: Box<dyn Vfs>,
    pub(crate) local_root: Option<PathBuf>,
    pub(crate) label: String,
}

impl MutationEndpoint {
    fn check_path(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        if !is_safe_relative_path(path) {
            return Err(format!(
                "unsafe endpoint path '{}': paths must be relative and contain no '..'",
                path.display()
            )
            .into());
        }
        Ok(())
    }

    fn path(path: &Path) -> Result<PathBuf, Box<dyn std::error::Error>> {
        Self::check_path(path)?;
        Ok(path.to_path_buf())
    }

    pub(crate) fn metadata(
        &self,
        path: &Path,
    ) -> Result<rcompare_common::FileMetadata, Box<dyn std::error::Error>> {
        Ok(self.vfs.metadata(&Self::path(path)?)?)
    }

    pub(crate) fn open_file(
        &self,
        path: &Path,
    ) -> Result<Box<dyn std::io::Read + Send>, Box<dyn std::error::Error>> {
        Ok(self.vfs.open_file(&Self::path(path)?)?)
    }

    pub(crate) fn create_file(
        &self,
        path: &Path,
    ) -> Result<Box<dyn std::io::Write + Send>, Box<dyn std::error::Error>> {
        Ok(self.vfs.create_file(&Self::path(path)?)?)
    }

    pub(crate) fn read_dir(
        &self,
        path: &Path,
    ) -> Result<Vec<rcompare_common::FileEntry>, Box<dyn std::error::Error>> {
        Ok(self.vfs.read_dir(&Self::path(path)?)?)
    }

    pub(crate) fn create_dir_all(&self, path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        Ok(self.vfs.create_dir_all(&Self::path(path)?)?)
    }

    pub(crate) fn remove_file(&self, path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        Ok(self.vfs.remove_file(&Self::path(path)?)?)
    }

    pub(crate) fn remove_dir(&self, path: &Path) -> Result<(), Box<dyn std::error::Error>> {
        Ok(self.vfs.remove_dir(&Self::path(path)?)?)
    }

    pub(crate) fn set_mtime(
        &self,
        path: &Path,
        mtime: std::time::SystemTime,
    ) -> Result<(), Box<dyn std::error::Error>> {
        Ok(self.vfs.set_mtime(&Self::path(path)?, mtime)?)
    }

    pub(crate) fn flush(&self) -> Result<(), Box<dyn std::error::Error>> {
        Ok(self.vfs.flush()?)
    }

    pub(crate) fn capabilities(&self) -> rcompare_common::VfsCapabilities {
        self.vfs.capabilities()
    }
}

/// Resolve a local, archive, or supported cloud endpoint for mutation.
pub(crate) fn build_mutation_endpoint(
    path: &Path,
    writable: bool,
) -> Result<MutationEndpoint, Box<dyn std::error::Error>> {
    #[cfg(not(feature = "archives"))]
    let _ = writable;

    let raw = path.to_string_lossy();
    if raw.contains("://") {
        #[cfg(feature = "cloud")]
        return build_cloud_endpoint(&raw);
        #[cfg(not(feature = "cloud"))]
        return Err(
            "URL endpoints are unavailable in this build; rebuild with the `cloud` feature".into(),
        );
    }

    if path.is_dir() {
        return Ok(MutationEndpoint {
            vfs: Box::new(LocalVfs::new(path.to_path_buf())),
            local_root: Some(path.to_path_buf()),
            label: path.display().to_string(),
        });
    }

    #[cfg(feature = "archives")]
    if let Some(kind) = detect_archive_kind(path) {
        if writable {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)?;
            }
        }
        let vfs: Box<dyn Vfs> = match (kind, writable) {
            (ArchiveKind::Zip, false) => Box::new(ZipVfs::new(path.to_path_buf())?),
            (ArchiveKind::Tar, false) => Box::new(TarVfs::new(path.to_path_buf())?),
            (ArchiveKind::SevenZ, false) => Box::new(SevenZVfs::new(path.to_path_buf())?),
            (ArchiveKind::Zip, true) => Box::new(if path.exists() {
                WritableZipVfs::new(path.to_path_buf())?
            } else {
                WritableZipVfs::create(path.to_path_buf())?
            }),
            (ArchiveKind::Tar, true) => Box::new(if path.exists() {
                WritableTarVfs::new(path.to_path_buf())?
            } else {
                WritableTarVfs::create(path.to_path_buf())?
            }),
            (ArchiveKind::SevenZ, true) => Box::new(if path.exists() {
                Writable7zVfs::new(path.to_path_buf())?
            } else {
                Writable7zVfs::create(path.to_path_buf())?
            }),
        };
        return Ok(MutationEndpoint {
            vfs,
            local_root: None,
            label: path.display().to_string(),
        });
    }

    Err(format!(
        "endpoint is not a directory or supported archive: {}",
        path.display()
    )
    .into())
}

#[cfg(feature = "cloud")]
fn build_cloud_endpoint(raw: &str) -> Result<MutationEndpoint, Box<dyn std::error::Error>> {
    let parsed = url::Url::parse(raw)?;
    validate_cloud_url(&parsed)?;
    let label = format!(
        "{}://{}{}",
        parsed.scheme(),
        parsed.host_str().unwrap_or("<missing-host>"),
        parsed.path()
    );
    let vfs: Box<dyn Vfs> = match parsed.scheme() {
        "s3" => {
            let bucket = parsed
                .host_str()
                .ok_or("s3 endpoint is missing its bucket")?
                .to_string();
            let region = std::env::var("AWS_REGION")
                .or_else(|_| std::env::var("AWS_DEFAULT_REGION"))
                .unwrap_or_else(|_| "us-east-1".to_string());
            Box::new(S3Vfs::new(S3Config {
                bucket,
                region,
                prefix: PathBuf::from(parsed.path()),
                auth: S3Auth::Default,
                endpoint: None,
            })?)
        }
        "sftp" => {
            let username = if parsed.username().is_empty() {
                std::env::var("RCOMPARE_SFTP_USERNAME").unwrap_or_default()
            } else {
                parsed.username().to_string()
            };
            let auth = match std::env::var("RCOMPARE_SFTP_PASSWORD") {
                Ok(password) => SftpAuth::Password(password),
                Err(_) => SftpAuth::Agent,
            };
            Box::new(SftpVfs::new(SftpConfig {
                host: parsed
                    .host_str()
                    .ok_or("sftp endpoint is missing its host")?
                    .to_string(),
                port: parsed.port().unwrap_or(22),
                username,
                auth,
                root_path: PathBuf::from(parsed.path()),
            })?)
        }
        "dav" | "davs" => {
            let transport_scheme = if parsed.scheme() == "davs" {
                "https"
            } else {
                "http"
            };
            let transport_url = parsed
                .as_str()
                .replacen(parsed.scheme(), transport_scheme, 1);
            let mut base = url::Url::parse(&transport_url)?;
            let root_path = PathBuf::from(parsed.path());
            base.set_path("/");
            base.set_query(None);
            base.set_fragment(None);
            let auth = match (
                std::env::var("RCOMPARE_WEBDAV_USERNAME"),
                std::env::var("RCOMPARE_WEBDAV_PASSWORD"),
            ) {
                (Ok(username), Ok(password)) => WebDavAuth::Basic { username, password },
                _ => WebDavAuth::None,
            };
            Box::new(WebDavVfs::new(WebDavConfig {
                url: base.to_string(),
                auth,
                root_path,
            })?)
        }
        scheme => return Err(format!("unsupported endpoint scheme '{scheme}'").into()),
    };
    Ok(MutationEndpoint {
        vfs,
        local_root: None,
        label,
    })
}

/// Copy one file or directory recursively between any two VFS endpoints.
fn copy_endpoint_entry_recursive_with_cancel(
    source: &MutationEndpoint,
    source_path: &Path,
    target: &MutationEndpoint,
    target_path: &Path,
    stop_flag: Option<&AtomicBool>,
) -> Result<(), Box<dyn std::error::Error>> {
    if stop_flag.is_some_and(|flag| flag.load(Ordering::SeqCst)) {
        return Err("sync cancelled".into());
    }
    let source_meta = source.metadata(source_path)?;
    if source_meta.is_dir {
        if let Ok(target_meta) = target.metadata(target_path) {
            if !target_meta.is_dir {
                target.remove_file(target_path)?;
            }
        }
        target.create_dir_all(target_path)?;
        for entry in source.read_dir(source_path)? {
            let name = entry
                .path
                .file_name()
                .ok_or("source entry has no filename")?;
            copy_endpoint_entry_recursive_with_cancel(
                source,
                &entry.path,
                target,
                &target_path.join(name),
                stop_flag,
            )?;
        }
        return Ok(());
    }

    if let Ok(target_meta) = target.metadata(target_path) {
        if target_meta.is_dir {
            remove_endpoint_entry(target, target_path, false)?;
        }
    }
    let mut reader = source.open_file(source_path)?;
    let mut writer = target.create_file(target_path)?;
    let mut buffer = vec![0u8; 4 * 1024 * 1024];
    loop {
        if stop_flag.is_some_and(|flag| flag.load(Ordering::SeqCst)) {
            writer.flush()?;
            return Err("sync cancelled".into());
        }
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        writer.write_all(&buffer[..read])?;
    }
    writer.flush()?;
    if target.capabilities().set_mtime {
        target.set_mtime(target_path, source_meta.modified)?;
    }
    Ok(())
}

/// Use the tested local resumable-copy engine when both endpoints are local
/// filesystems; all other endpoint combinations use the VFS stream path.
pub(crate) fn copy_endpoint_entry_with_resume(
    source: &MutationEndpoint,
    source_path: &Path,
    target: &MutationEndpoint,
    target_path: &Path,
    checkpoint_dir: Option<&Path>,
) -> Result<(), Box<dyn std::error::Error>> {
    copy_endpoint_entry_with_cancel(
        source,
        source_path,
        target,
        target_path,
        checkpoint_dir,
        None,
    )
}

pub(crate) fn copy_endpoint_entry_with_cancel(
    source: &MutationEndpoint,
    source_path: &Path,
    target: &MutationEndpoint,
    target_path: &Path,
    checkpoint_dir: Option<&Path>,
    stop_flag: Option<&AtomicBool>,
) -> Result<(), Box<dyn std::error::Error>> {
    let source_meta = source.metadata(source_path)?;
    if let (Some(source_root), Some(target_root), Some(checkpoint_dir)) = (
        source.local_root.as_ref(),
        target.local_root.as_ref(),
        checkpoint_dir,
    ) {
        if !source_meta.is_dir {
            if target
                .metadata(target_path)
                .map(|meta| meta.is_dir)
                .unwrap_or(false)
            {
                remove_endpoint_entry(target, target_path, false)?;
            }
            let result = ResumableCopy::new(checkpoint_dir.to_path_buf())
                .copy_resumable_with_cancel(
                    &source_root.join(source_path),
                    &target_root.join(target_path),
                    None,
                    stop_flag,
                )?;
            if !result.success {
                return Err(result
                    .error
                    .unwrap_or_else(|| "resumable copy verification failed".to_string())
                    .into());
            }
            return Ok(());
        }
    }
    copy_endpoint_entry_recursive_with_cancel(source, source_path, target, target_path, stop_flag)
}

pub(crate) fn remove_endpoint_entry(
    target: &MutationEndpoint,
    path: &Path,
    use_trash: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let Ok(meta) = target.metadata(path) else {
        return Ok(());
    };
    if use_trash {
        let root = target
            .local_root
            .as_ref()
            .ok_or("trash deletion is only supported for local targets")?;
        move_to_local_trash(&root.join(path))?;
        return Ok(());
    }
    if meta.is_dir {
        for entry in target.read_dir(path)? {
            remove_endpoint_entry(target, &entry.path, false)?;
        }
        target.remove_dir(path)?;
    } else {
        target.remove_file(path)?;
    }
    Ok(())
}

pub(crate) fn validate_mutation_capabilities(
    endpoint: &MutationEndpoint,
    needs_write: bool,
    needs_delete: bool,
    use_trash: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    let caps = endpoint.capabilities();
    let mut missing = Vec::new();
    if needs_write && !caps.write {
        missing.push("write");
    }
    if needs_delete && !caps.delete {
        missing.push("delete");
    }
    if use_trash && endpoint.local_root.is_none() {
        missing.push("local trash deletion");
    }
    if !missing.is_empty() {
        return Err(format!(
            "endpoint '{}' does not support required operations: {}",
            endpoint.label,
            missing.join(", ")
        )
        .into());
    }
    Ok(())
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

/// Split a file operand into a source root and a safe file name. Local files
/// must exist; remote URLs use their final path component as the relative name.
pub(crate) fn split_source_file_operand(
    source_path: &Path,
) -> Result<(PathBuf, PathBuf), Box<dyn std::error::Error>> {
    let raw = source_path.to_string_lossy();
    if raw.contains("://") {
        #[cfg(feature = "cloud")]
        {
            let mut parsed = url::Url::parse(&raw)?;
            validate_cloud_url(&parsed)?;
            let encoded_path = parsed.path().to_string();
            if encoded_path.is_empty() || encoded_path.ends_with('/') {
                return Err("remote file URL must end with a file name".into());
            }
            let (parent_path, file_name) = encoded_path
                .rsplit_once('/')
                .unwrap_or(("", encoded_path.as_str()));
            if file_name.is_empty() || file_name == "." || file_name == ".." {
                return Err("remote file URL must end with a file name".into());
            }
            let parent_path = parent_path.to_string();
            let file_name = file_name.to_string();
            parsed.set_path(&parent_path);
            return Ok((PathBuf::from(parsed.to_string()), PathBuf::from(file_name)));
        }
        #[cfg(not(feature = "cloud"))]
        return Err(
            "URL endpoints are unavailable in this build; rebuild with the `cloud` feature".into(),
        );
    }

    if !source_path.is_file() {
        return Err(
            "provide --path for source roots, or pass two existing files without --path".into(),
        );
    }
    let file_name = source_path
        .file_name()
        .ok_or("file operand has no file name")?;
    let root = source_path.parent().unwrap_or_else(|| Path::new("."));
    Ok((root.to_path_buf(), PathBuf::from(file_name)))
}

/// Copy a source file to a writer without buffering the complete file.
pub(crate) fn copy_source_file_to_writer<W: Write>(
    source_path: &Path,
    rel: &Path,
    writer: &mut W,
) -> Result<u64, Box<dyn std::error::Error>> {
    let source = build_scan_source(source_path)?;
    match source {
        ScanSource::Local { root } => {
            let full = root.join(rel);
            if !full.exists() {
                return Err(format!("path not found: {}", full.display()).into());
            }
            if full.is_dir() {
                return Err(format!("path is a directory: {}", full.display()).into());
            }
            let mut file = fs::File::open(&full)?;
            Ok(std::io::copy(&mut file, writer)?)
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
            Ok(std::io::copy(&mut reader, writer)?)
        }
    }
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
    ignore_whitespace: Option<WhitespaceModeArg>,
    ignore_case: bool,
    regex_rules: Vec<String>,
) -> Result<TextDiffConfig, Box<dyn std::error::Error>> {
    let mut config = TextDiffConfig::new();

    // Whitespace mode is already validated by clap; just map variant to variant.
    if let Some(mode) = ignore_whitespace {
        config.whitespace_mode = match mode {
            WhitespaceModeArg::All => WhitespaceMode::IgnoreAll,
            WhitespaceModeArg::Leading => WhitespaceMode::IgnoreLeading,
            WhitespaceModeArg::Trailing => WhitespaceMode::IgnoreTrailing,
            WhitespaceModeArg::Changes => WhitespaceMode::IgnoreChanges,
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

pub(crate) fn build_scan_source(
    path: &std::path::Path,
) -> Result<ScanSource, Box<dyn std::error::Error>> {
    let raw = path.to_string_lossy();
    if raw.contains("://") {
        #[cfg(feature = "cloud")]
        {
            let endpoint = build_cloud_endpoint(&raw)?;
            return Ok(ScanSource::Vfs {
                vfs: endpoint.vfs,
                root: PathBuf::new(),
            });
        }
        #[cfg(not(feature = "cloud"))]
        return Err(
            "URL endpoints are unavailable in this build; rebuild with the `cloud` feature".into(),
        );
    }

    if path.is_dir() {
        return Ok(ScanSource::Local {
            root: path.to_path_buf(),
        });
    }

    if path.is_file() {
        #[cfg(feature = "archives")]
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

        // Minimal build: archive backends were not compiled in, so any file
        // path (archive or not) is unusable as a comparison source. Name the
        // cause explicitly rather than reporting "unsupported archive", which
        // would wrongly suggest the format itself is the problem.
        #[cfg(not(feature = "archives"))]
        return Err(format!(
            "Path is not a directory: {} (this build was compiled without the \
             `archives` feature, so .zip/.tar/.tar.gz/.tgz/.7z sources are unavailable)",
            path.display()
        )
        .into());
    }

    Err(format!("Path does not exist: {}", path.display()).into())
}

/// Build a scan source with optional union layers and glob filtering.
/// Positional sources and overlays share the same relative-root contract.
pub(crate) fn build_scan_source_with_overlays(
    path: &Path,
    overlays: &[PathBuf],
    include_patterns: &[String],
    exclude_patterns: &[String],
) -> Result<ScanSource, Box<dyn std::error::Error>> {
    if overlays.is_empty() && include_patterns.is_empty() && exclude_patterns.is_empty() {
        return build_scan_source(path);
    }

    let base = build_scan_source(path)?;
    let base_vfs: Arc<dyn Vfs> = match base {
        ScanSource::Local { root } => Arc::new(LocalVfs::new(root)),
        ScanSource::Vfs { vfs, root: _ } => Arc::from(vfs),
    };
    let mut union = UnionVfs::new().add_layer(base_vfs);

    for overlay in overlays {
        let source = build_scan_source(overlay)?;
        let vfs: Arc<dyn Vfs> = match source {
            ScanSource::Local { root } => Arc::new(LocalVfs::new(root)),
            ScanSource::Vfs { vfs, root: _ } => Arc::from(vfs),
        };
        union = union.add_layer(vfs);
    }

    let mut filtered = FilteredVfs::new(Arc::new(union));
    for pattern in include_patterns {
        filtered = filtered.include(pattern)?;
    }
    for pattern in exclude_patterns {
        filtered = filtered.exclude(pattern)?;
    }

    Ok(ScanSource::Vfs {
        vfs: Box::new(filtered),
        root: PathBuf::new(),
    })
}

#[cfg(feature = "archives")]
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
    /// JSON schema selector: 1 preserves the command-specific legacy report;
    /// every other value emits the stable v2 envelope.
    pub(crate) schema_version: u8,
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
    pub(crate) scan_jobs: u8,
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

    let has_vfs = matches!(left_source, ScanSource::Vfs { .. })
        || matches!(right_source, ScanSource::Vfs { .. });
    if has_vfs && !opts.no_verify_hashes {
        verify_hashes = true;
    }

    let mut warnings = Vec::new();

    let scan_one = |scanner: &FolderScanner, source: &ScanSource| match source {
        ScanSource::Local { root } => scanner.scan_with_cancel(root, Some(stop_flag.as_ref())),
        ScanSource::Vfs { vfs, root } => {
            scanner.scan_vfs_with_cancel(vfs.as_ref(), root, Some(stop_flag.as_ref()))
        }
    };
    let (left_outcome, right_outcome) = if opts.scan_jobs > 1 {
        std::thread::scope(|scope| {
            let left_task = scope.spawn(|| scan_one(&left_scanner, &left_source));
            let right_task = scope.spawn(|| scan_one(&right_scanner, &right_source));
            let left_result = left_task.join().map_err(|_| "left scan worker panicked")?;
            let right_result = right_task
                .join()
                .map_err(|_| "right scan worker panicked")?;
            Ok::<_, Box<dyn std::error::Error>>((left_result?, right_result?))
        })?
    } else {
        (
            scan_one(&left_scanner, &left_source)?,
            scan_one(&right_scanner, &right_source)?,
        )
    };

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

#[cfg(all(test, feature = "cloud"))]
mod remote_url_tests {
    #![allow(clippy::expect_used, clippy::unwrap_used)]

    use super::{split_source_file_operand, validate_cloud_url, REMOTE_SOURCE_SCHEMES};
    use std::path::Path;

    #[test]
    fn advertised_schemes_pass_remote_url_validation() {
        for scheme in REMOTE_SOURCE_SCHEMES {
            let url = url::Url::parse(&format!("{scheme}://example.test/root"))
                .expect("valid source URL");
            validate_cloud_url(&url).expect("advertised scheme should be accepted");
        }
    }

    #[test]
    fn remote_urls_reject_embedded_credentials_and_tokens() {
        for raw in [
            "sftp://user@example.test/root",
            "sftp://user:secret@example.test/root",
            "davs://example.test/root?token=secret",
            "dav://example.test/root#secret",
        ] {
            let url = url::Url::parse(raw).expect("valid URL syntax");
            let error = validate_cloud_url(&url).expect_err("embedded secret must be rejected");
            let message = error.to_string();
            assert!(message.contains("must be supplied"));
            assert!(!message.contains("secret"));
        }
    }

    #[test]
    fn remote_file_operands_split_into_parent_endpoints_and_relative_names() {
        for (raw, expected_root, expected_name) in [
            ("s3://bucket/a/before.txt", "s3://bucket/a", "before.txt"),
            (
                "sftp://files.example.test/archive/after.md",
                "sftp://files.example.test/archive",
                "after.md",
            ),
            (
                "davs://files.example.test/photo.png",
                "davs://files.example.test",
                "photo.png",
            ),
        ] {
            let (root, relative) = split_source_file_operand(Path::new(raw))
                .expect("remote file operand should split");
            assert_eq!(root.to_string_lossy(), expected_root);
            assert_eq!(relative.to_string_lossy(), expected_name);
        }
    }

    #[test]
    fn remote_file_operands_reject_directories_and_inline_secrets() {
        for raw in [
            "s3://bucket/folder/",
            "s3://user:secret@bucket/file.txt",
            "s3://bucket/file.txt?token=secret",
        ] {
            let error = split_source_file_operand(Path::new(raw))
                .expect_err("unsafe remote operand must fail");
            assert!(!error.to_string().contains("secret"));
        }
    }
}
