use aws_config::BehaviorVersion;
use aws_credential_types::Credentials;
use aws_sdk_s3::Client;
use rcompare_common::{FileEntry, FileMetadata, Vfs, VfsCapabilities, VfsError};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::runtime::Runtime;

/// S3 connection configuration
#[derive(Debug, Clone)]
pub struct S3Config {
    pub bucket: String,
    pub region: String,
    pub prefix: PathBuf,
    pub auth: S3Auth,
    pub endpoint: Option<String>, // For S3-compatible services (MinIO, DigitalOcean Spaces, etc.)
}

/// Authentication method for S3
#[derive(Debug, Clone)]
pub enum S3Auth {
    /// Use AWS credentials from environment variables or IAM role
    Default,
    /// Explicit access key and secret key
    AccessKey {
        access_key_id: String,
        secret_access_key: String,
        session_token: Option<String>,
    },
    /// Anonymous access (public buckets)
    Anonymous,
}

impl Default for S3Config {
    fn default() -> Self {
        Self {
            bucket: String::new(),
            region: "us-east-1".to_string(),
            prefix: PathBuf::from("/"),
            auth: S3Auth::Default,
            endpoint: None,
        }
    }
}

/// S3 Virtual File System implementation
pub struct S3Vfs {
    instance_id: String,
    config: S3Config,
    client: Arc<Client>,
    runtime: Arc<Runtime>,
}

impl S3Vfs {
    /// Create a new S3 VFS connection
    pub fn new(config: S3Config) -> Result<Self, VfsError> {
        let instance_id = format!("s3://{}/{}", config.bucket, config.prefix.display());

        // Create a Tokio runtime for async operations
        let runtime = Runtime::new().map_err(|e| {
            VfsError::Io(std::io::Error::other(format!(
                "Failed to create async runtime: {}",
                e
            )))
        })?;

        let client = runtime.block_on(Self::create_client(&config))?;

        Ok(Self {
            instance_id,
            config,
            client: Arc::new(client),
            runtime: Arc::new(runtime),
        })
    }

    async fn create_client(config: &S3Config) -> Result<Client, VfsError> {
        let mut aws_config_builder = aws_config::defaults(BehaviorVersion::latest());

        // Set region
        aws_config_builder =
            aws_config_builder.region(aws_config::Region::new(config.region.clone()));

        // Set custom endpoint if provided (for S3-compatible services)
        if let Some(endpoint) = &config.endpoint {
            aws_config_builder = aws_config_builder.endpoint_url(endpoint);
        }

        // Set credentials based on auth method
        match &config.auth {
            S3Auth::Default => {
                // Use default credential chain (env vars, IAM role, etc.)
            }
            S3Auth::AccessKey {
                access_key_id,
                secret_access_key,
                session_token,
            } => {
                let creds = Credentials::new(
                    access_key_id,
                    secret_access_key,
                    session_token.clone(),
                    None,
                    "static",
                );
                aws_config_builder = aws_config_builder.credentials_provider(creds);
            }
            S3Auth::Anonymous => {
                // For anonymous access, we use empty credentials
                let creds = Credentials::new("", "", None, None, "anonymous");
                aws_config_builder = aws_config_builder.credentials_provider(creds);
            }
        }

        let aws_config = aws_config_builder.load().await;
        Ok(Client::new(&aws_config))
    }

    /// Convert a VFS path to an S3 key
    fn to_s3_key(&self, path: &Path) -> String {
        let full_path = self.config.prefix.join(path);
        full_path
            .to_string_lossy()
            .trim_start_matches('/')
            .to_string()
    }

    /// Convert an S3 key to a VFS path
    fn s3_key_to_path(&self, key: &str) -> PathBuf {
        let prefix_str = self.config.prefix.to_string_lossy();
        let prefix_str = prefix_str.trim_start_matches('/');

        if let Some(suffix) = key.strip_prefix(prefix_str) {
            PathBuf::from(suffix.trim_start_matches('/'))
        } else {
            PathBuf::from(key)
        }
    }

    /// Check if an S3 key represents a directory (ends with /)
    fn is_directory_key(key: &str) -> bool {
        key.ends_with('/')
    }

    /// Ensure directory keys end with /
    fn normalize_dir_key(key: &str, is_dir: bool) -> String {
        if is_dir && !key.ends_with('/') {
            format!("{}/", key)
        } else {
            key.to_string()
        }
    }
}

impl Vfs for S3Vfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let key = self.to_s3_key(path);

        self.runtime.block_on(async {
            // Try to get object metadata
            let head_result = self
                .client
                .head_object()
                .bucket(&self.config.bucket)
                .key(&key)
                .send()
                .await;

            match head_result {
                Ok(output) => {
                    let size = output.content_length().unwrap_or(0) as u64;
                    let modified = output
                        .last_modified()
                        .and_then(|dt| {
                            dt.secs()
                                .try_into()
                                .ok()
                                .map(|secs| UNIX_EPOCH + std::time::Duration::from_secs(secs))
                        })
                        .unwrap_or(SystemTime::now());

                    Ok(FileMetadata {
                        size,
                        modified,
                        is_dir: false,
                        is_symlink: false,
                    })
                }
                Err(_) => {
                    // Object not found, might be a directory
                    // Try listing with the key as a prefix
                    let dir_key = Self::normalize_dir_key(&key, true);
                    let list_result = self
                        .client
                        .list_objects_v2()
                        .bucket(&self.config.bucket)
                        .prefix(&dir_key)
                        .max_keys(1)
                        .send()
                        .await;

                    match list_result {
                        Ok(output) if output.key_count().unwrap_or(0) > 0 => {
                            // It's a directory
                            Ok(FileMetadata {
                                size: 0,
                                modified: SystemTime::now(),
                                is_dir: true,
                                is_symlink: false,
                            })
                        }
                        _ => Err(VfsError::NotFound(format!("S3 object not found: {}", key))),
                    }
                }
            }
        })
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let prefix = self.to_s3_key(path);
        let prefix = Self::normalize_dir_key(&prefix, true);

        self.runtime.block_on(async {
            let mut entries = Vec::new();
            let mut continuation_token: Option<String> = None;

            loop {
                let mut list_request = self
                    .client
                    .list_objects_v2()
                    .bucket(&self.config.bucket)
                    .prefix(&prefix)
                    .delimiter("/");

                if let Some(token) = &continuation_token {
                    list_request = list_request.continuation_token(token);
                }

                let output = list_request.send().await.map_err(|e| {
                    VfsError::Io(std::io::Error::other(format!(
                        "Failed to list S3 objects: {}",
                        e
                    )))
                })?;

                // Add files (objects)
                for object in output.contents() {
                    if let Some(key) = object.key() {
                        // Skip the prefix itself
                        if key == prefix {
                            continue;
                        }

                        let path = self.s3_key_to_path(key);
                        let size = object.size().map(|s| s as u64).unwrap_or(0);
                        let modified = object
                            .last_modified()
                            .map(|dt| {
                                let secs = dt.secs() as u64;
                                UNIX_EPOCH + std::time::Duration::from_secs(secs)
                            })
                            .unwrap_or(SystemTime::now());

                        entries.push(FileEntry {
                            path,
                            size,
                            modified,
                            is_dir: Self::is_directory_key(key),
                        });
                    }
                }

                // Add directories (common prefixes)
                for common_prefix in output.common_prefixes() {
                    if let Some(prefix_str) = common_prefix.prefix() {
                        let path = self.s3_key_to_path(prefix_str);
                        entries.push(FileEntry {
                            path,
                            size: 0,
                            modified: SystemTime::now(),
                            is_dir: true,
                        });
                    }
                }

                // Check if there are more results
                if output.is_truncated().unwrap_or(false) {
                    continuation_token = output.next_continuation_token().map(|s| s.to_string());
                } else {
                    break;
                }
            }

            Ok(entries)
        })
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let key = self.to_s3_key(path);

        self.runtime.block_on(async {
            let output = self
                .client
                .get_object()
                .bucket(&self.config.bucket)
                .key(&key)
                .send()
                .await
                .map_err(|e| {
                    VfsError::Io(std::io::Error::new(
                        std::io::ErrorKind::NotFound,
                        format!("Failed to get S3 object: {}", e),
                    ))
                })?;

            // Read the entire body into memory
            let bytes = output
                .body
                .collect()
                .await
                .map_err(|e| {
                    VfsError::Io(std::io::Error::other(format!(
                        "Failed to read S3 object body: {}",
                        e
                    )))
                })?
                .into_bytes();

            Ok(Box::new(std::io::Cursor::new(bytes.to_vec())) as Box<dyn Read + Send>)
        })
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        let key = self.to_s3_key(path);

        self.runtime.block_on(async {
            self.client
                .delete_object()
                .bucket(&self.config.bucket)
                .key(&key)
                .send()
                .await
                .map_err(|e| {
                    VfsError::Io(std::io::Error::other(format!(
                        "Failed to delete S3 object: {}",
                        e
                    )))
                })?;

            Ok(())
        })
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        let src_key = self.to_s3_key(src);
        let dest_key = self.to_s3_key(dest);

        self.runtime.block_on(async {
            let copy_source = format!("{}/{}", self.config.bucket, src_key);

            self.client
                .copy_object()
                .bucket(&self.config.bucket)
                .copy_source(&copy_source)
                .key(&dest_key)
                .send()
                .await
                .map_err(|e| {
                    VfsError::Io(std::io::Error::other(format!(
                        "Failed to copy S3 object: {}",
                        e
                    )))
                })?;

            Ok(())
        })
    }

    fn capabilities(&self) -> VfsCapabilities {
        VfsCapabilities {
            read: true,
            write: true,
            delete: true,
            rename: true,
            create_dir: true,
            set_mtime: false, // S3 doesn't support setting modification time
        }
    }

    fn create_file(&self, path: &Path) -> Result<Box<dyn std::io::Write + Send>, VfsError> {
        // Return a writer that buffers data and uploads on drop
        Ok(Box::new(S3Writer::new(
            self.client.clone(),
            self.runtime.clone(),
            self.config.bucket.clone(),
            self.to_s3_key(path),
        )))
    }

    fn create_dir(&self, path: &Path) -> Result<(), VfsError> {
        let key = self.to_s3_key(path);
        let dir_key = Self::normalize_dir_key(&key, true);

        self.runtime.block_on(async {
            self.client
                .put_object()
                .bucket(&self.config.bucket)
                .key(&dir_key)
                .body(aws_sdk_s3::primitives::ByteStream::from(vec![]))
                .send()
                .await
                .map_err(|e| {
                    VfsError::Io(std::io::Error::other(format!(
                        "Failed to create S3 directory: {}",
                        e
                    )))
                })?;

            Ok(())
        })
    }

    fn create_dir_all(&self, path: &Path) -> Result<(), VfsError> {
        // S3 doesn't require creating parent directories
        self.create_dir(path)
    }

    fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError> {
        // S3 doesn't have a native rename operation, so we copy and delete
        self.copy_file(from, to)?;
        self.remove_file(from)?;
        Ok(())
    }

    fn write_file(&self, path: &Path, content: &[u8]) -> Result<(), VfsError> {
        let key = self.to_s3_key(path);

        self.runtime.block_on(async {
            self.client
                .put_object()
                .bucket(&self.config.bucket)
                .key(&key)
                .body(aws_sdk_s3::primitives::ByteStream::from(content.to_vec()))
                .send()
                .await
                .map_err(|e| {
                    VfsError::Io(std::io::Error::other(format!(
                        "Failed to write S3 object: {}",
                        e
                    )))
                })?;

            Ok(())
        })
    }
}

/// A writer that buffers data and uploads to S3 when dropped
struct S3Writer {
    client: Arc<Client>,
    runtime: Arc<Runtime>,
    bucket: String,
    key: String,
    buffer: Vec<u8>,
}

impl S3Writer {
    fn new(client: Arc<Client>, runtime: Arc<Runtime>, bucket: String, key: String) -> Self {
        Self {
            client,
            runtime,
            bucket,
            key,
            buffer: Vec::new(),
        }
    }
}

impl std::io::Write for S3Writer {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.buffer.extend_from_slice(buf);
        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        // Upload the buffer to S3
        let client = self.client.clone();
        let bucket = self.bucket.clone();
        let key = self.key.clone();
        let data = self.buffer.clone();

        self.runtime.block_on(async {
            client
                .put_object()
                .bucket(&bucket)
                .key(&key)
                .body(aws_sdk_s3::primitives::ByteStream::from(data))
                .send()
                .await
                .map_err(|e| std::io::Error::other(format!("Failed to upload to S3: {}", e)))?;

            Ok(())
        })
    }
}

impl Drop for S3Writer {
    fn drop(&mut self) {
        let _ = self.flush();
    }
}
