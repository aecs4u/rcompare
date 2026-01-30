use rcompare_common::{FileEntry, FileMetadata, Vfs, VfsCapabilities, VfsError};
use reqwest::{Client, Method, StatusCode};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::SystemTime;
use tokio::runtime::Runtime;
use url::Url;

/// WebDAV connection configuration
#[derive(Debug, Clone)]
pub struct WebDavConfig {
    pub url: String,
    pub auth: WebDavAuth,
    pub root_path: PathBuf,
}

/// Authentication method for WebDAV
#[derive(Debug, Clone)]
pub enum WebDavAuth {
    /// No authentication
    None,
    /// HTTP Basic authentication
    Basic { username: String, password: String },
    /// HTTP Digest authentication
    Digest { username: String, password: String },
    /// Bearer token authentication
    Bearer { token: String },
}

impl Default for WebDavConfig {
    fn default() -> Self {
        Self {
            url: String::new(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/"),
        }
    }
}

/// WebDAV Virtual File System implementation
pub struct WebDavVfs {
    instance_id: String,
    config: WebDavConfig,
    client: Arc<Client>,
    base_url: Url,
    runtime: Arc<Runtime>,
}

impl WebDavVfs {
    /// Create a new WebDAV VFS connection
    pub fn new(config: WebDavConfig) -> Result<Self, VfsError> {
        let instance_id = format!("webdav://{}{}", config.url, config.root_path.display());

        // Parse base URL
        let base_url = Url::parse(&config.url).map_err(|e| {
            VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                format!("Invalid WebDAV URL: {}", e),
            ))
        })?;

        // Create a Tokio runtime for async operations
        let runtime = Runtime::new().map_err(|e| {
            VfsError::Io(std::io::Error::other(format!(
                "Failed to create async runtime: {}",
                e
            )))
        })?;

        let client = Self::create_client(&config)?;

        Ok(Self {
            instance_id,
            config,
            client: Arc::new(client),
            base_url,
            runtime: Arc::new(runtime),
        })
    }

    fn create_client(_config: &WebDavConfig) -> Result<Client, VfsError> {
        let builder = Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .connect_timeout(std::time::Duration::from_secs(10));

        // Note: Authentication is handled per-request in add_auth_header
        // reqwest's basic_auth on builder is deprecated, use per-request headers instead

        builder.build().map_err(|e| {
            VfsError::Io(std::io::Error::other(format!(
                "Failed to create HTTP client: {}",
                e
            )))
        })
    }

    /// Convert a VFS path to a WebDAV URL
    fn to_webdav_url(&self, path: &Path) -> Result<Url, VfsError> {
        let full_path = self.config.root_path.join(path);
        let path_str = full_path.to_string_lossy();
        let path_str = path_str.trim_start_matches('/');

        self.base_url.join(path_str).map_err(|e| {
            VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                format!("Failed to construct WebDAV URL: {}", e),
            ))
        })
    }

    /// Add authorization header based on auth type
    fn add_auth_header(&self, builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
        match &self.config.auth {
            WebDavAuth::None => builder,
            WebDavAuth::Basic { username, password } => {
                builder.basic_auth(username, Some(password))
            }
            WebDavAuth::Digest { username, password } => {
                // Note: reqwest doesn't natively support digest auth
                // Using basic auth as fallback
                builder.basic_auth(username, Some(password))
            }
            WebDavAuth::Bearer { token } => {
                builder.header("Authorization", format!("Bearer {}", token))
            }
        }
    }

    /// Parse PROPFIND response to extract file entries
    fn parse_propfind_response(&self, xml: &str, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let mut entries = Vec::new();

        // Simple XML parsing (in production, use a proper XML parser like quick-xml)
        // This is a simplified implementation for demonstration
        for line in xml.lines() {
            // Extract href (file path)
            if let Some(href_start) = line.find("<D:href>") {
                if let Some(href_end) = line.find("</D:href>") {
                    let href = &line[href_start + 8..href_end];

                    // Skip the parent directory itself
                    if href.trim_end_matches('/') == path.to_string_lossy().trim_end_matches('/') {
                        continue;
                    }

                    // Extract just the filename from the full path
                    let entry_path = PathBuf::from(href.trim_start_matches('/'));

                    // Determine if it's a directory
                    let is_dir = href.ends_with('/');

                    entries.push(FileEntry {
                        path: entry_path,
                        size: 0, // Will be updated from getcontentlength
                        modified: SystemTime::now(),
                        is_dir,
                    });
                }
            }
        }

        Ok(entries)
    }

    /// Parse a WebDAV date string (RFC 1123 format)
    fn parse_date(_date_str: &str) -> Option<SystemTime> {
        // Simplified date parsing
        // In production, use chrono or httpdate crate
        // For now, return current time
        Some(SystemTime::now())
    }
}

impl Vfs for WebDavVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let propfind_body = r#"<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:getcontentlength/>
        <D:getlastmodified/>
        <D:resourcetype/>
    </D:prop>
</D:propfind>"#;

            let request = self
                .client
                .request(Method::from_bytes(b"PROPFIND").unwrap(), url)
                .header("Depth", "0")
                .header("Content-Type", "application/xml")
                .body(propfind_body);

            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "WebDAV PROPFIND failed: {}",
                    e
                )))
            })?;

            if !response.status().is_success() {
                if response.status() == StatusCode::NOT_FOUND {
                    return Err(VfsError::NotFound(format!(
                        "WebDAV resource not found: {}",
                        path.display()
                    )));
                }
                return Err(VfsError::Io(std::io::Error::other(format!(
                    "WebDAV PROPFIND returned status: {}",
                    response.status()
                ))));
            }

            let xml = response.text().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to read PROPFIND response: {}",
                    e
                )))
            })?;

            // Parse the XML response
            let is_dir = xml.contains("<D:collection/>") || xml.contains("<D:collection ");

            // Extract content length
            let size = if let Some(start) = xml.find("<D:getcontentlength>") {
                if let Some(end) = xml.find("</D:getcontentlength>") {
                    xml[start + 20..end].parse::<u64>().unwrap_or(0)
                } else {
                    0
                }
            } else {
                0
            };

            // Extract last modified date
            let modified = if let Some(start) = xml.find("<D:getlastmodified>") {
                if let Some(end) = xml.find("</D:getlastmodified>") {
                    Self::parse_date(&xml[start + 19..end]).unwrap_or_else(SystemTime::now)
                } else {
                    SystemTime::now()
                }
            } else {
                SystemTime::now()
            };

            Ok(FileMetadata {
                size,
                modified,
                is_dir,
                is_symlink: false,
            })
        })
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let propfind_body = r#"<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:getcontentlength/>
        <D:getlastmodified/>
        <D:resourcetype/>
    </D:prop>
</D:propfind>"#;

            let request = self
                .client
                .request(Method::from_bytes(b"PROPFIND").unwrap(), url)
                .header("Depth", "1")
                .header("Content-Type", "application/xml")
                .body(propfind_body);

            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "WebDAV PROPFIND failed: {}",
                    e
                )))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::Io(std::io::Error::other(format!(
                    "WebDAV PROPFIND returned status: {}",
                    response.status()
                ))));
            }

            let xml = response.text().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to read PROPFIND response: {}",
                    e
                )))
            })?;

            self.parse_propfind_response(&xml, path)
        })
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let request = self.client.get(url);
            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::new(
                    std::io::ErrorKind::NotFound,
                    format!("Failed to GET WebDAV file: {}", e),
                ))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::NotFound(format!(
                    "WebDAV file not found: {}",
                    path.display()
                )));
            }

            let bytes = response.bytes().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to read WebDAV file body: {}",
                    e
                )))
            })?;

            Ok(Box::new(std::io::Cursor::new(bytes.to_vec())) as Box<dyn Read + Send>)
        })
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let request = self.client.delete(url);
            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to DELETE WebDAV resource: {}",
                    e
                )))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::Io(std::io::Error::other(format!(
                    "WebDAV DELETE returned status: {}",
                    response.status()
                ))));
            }

            Ok(())
        })
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        let src_url = self.to_webdav_url(src)?;
        let dest_url = self.to_webdav_url(dest)?;

        self.runtime.block_on(async {
            let request = self
                .client
                .request(Method::from_bytes(b"COPY").unwrap(), src_url)
                .header("Destination", dest_url.to_string())
                .header("Overwrite", "T");

            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to COPY WebDAV resource: {}",
                    e
                )))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::Io(std::io::Error::other(format!(
                    "WebDAV COPY returned status: {}",
                    response.status()
                ))));
            }

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
            set_mtime: false, // WebDAV typically doesn't support setting mtime directly
        }
    }

    fn create_file(&self, path: &Path) -> Result<Box<dyn std::io::Write + Send>, VfsError> {
        Ok(Box::new(WebDavWriter::new(
            self.client.clone(),
            self.runtime.clone(),
            self.to_webdav_url(path)?,
            self.config.auth.clone(),
        )))
    }

    fn create_dir(&self, path: &Path) -> Result<(), VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let request = self
                .client
                .request(Method::from_bytes(b"MKCOL").unwrap(), url);

            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to MKCOL WebDAV directory: {}",
                    e
                )))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::Io(std::io::Error::other(format!(
                    "WebDAV MKCOL returned status: {}",
                    response.status()
                ))));
            }

            Ok(())
        })
    }

    fn create_dir_all(&self, path: &Path) -> Result<(), VfsError> {
        // Create parent directories recursively
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                // Try to create parent, ignore errors if it already exists
                let _ = self.create_dir_all(parent);
            }
        }

        // Try to create this directory, ignore error if it already exists
        match self.create_dir(path) {
            Ok(()) => Ok(()),
            Err(VfsError::Io(_)) => {
                // Check if it already exists
                if self.metadata(path).is_ok() {
                    Ok(())
                } else {
                    Err(VfsError::Io(std::io::Error::other(format!(
                        "Failed to create directory: {}",
                        path.display()
                    ))))
                }
            }
            Err(e) => Err(e),
        }
    }

    fn rename(&self, from: &Path, to: &Path) -> Result<(), VfsError> {
        let from_url = self.to_webdav_url(from)?;
        let to_url = self.to_webdav_url(to)?;

        self.runtime.block_on(async {
            let request = self
                .client
                .request(Method::from_bytes(b"MOVE").unwrap(), from_url)
                .header("Destination", to_url.to_string())
                .header("Overwrite", "F");

            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to MOVE WebDAV resource: {}",
                    e
                )))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::Io(std::io::Error::other(format!(
                    "WebDAV MOVE returned status: {}",
                    response.status()
                ))));
            }

            Ok(())
        })
    }

    fn write_file(&self, path: &Path, content: &[u8]) -> Result<(), VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let request = self.client.put(url).body(content.to_vec());

            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to PUT WebDAV file: {}",
                    e
                )))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::Io(std::io::Error::other(format!(
                    "WebDAV PUT returned status: {}",
                    response.status()
                ))));
            }

            Ok(())
        })
    }
}

/// A writer that buffers data and uploads to WebDAV when dropped
struct WebDavWriter {
    client: Arc<Client>,
    runtime: Arc<Runtime>,
    url: Url,
    auth: WebDavAuth,
    buffer: Vec<u8>,
}

impl WebDavWriter {
    fn new(client: Arc<Client>, runtime: Arc<Runtime>, url: Url, auth: WebDavAuth) -> Self {
        Self {
            client,
            runtime,
            url,
            auth,
            buffer: Vec::new(),
        }
    }

    fn add_auth_header(&self, builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
        match &self.auth {
            WebDavAuth::None => builder,
            WebDavAuth::Basic { username, password } => {
                builder.basic_auth(username, Some(password))
            }
            WebDavAuth::Digest { username, password } => {
                // Note: reqwest doesn't natively support digest auth
                // Using basic auth as fallback
                builder.basic_auth(username, Some(password))
            }
            WebDavAuth::Bearer { token } => {
                builder.header("Authorization", format!("Bearer {}", token))
            }
        }
    }
}

impl std::io::Write for WebDavWriter {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.buffer.extend_from_slice(buf);
        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        // Upload the buffer to WebDAV
        let client = self.client.clone();
        let url = self.url.clone();
        let data = self.buffer.clone();

        self.runtime.block_on(async {
            let request = client.put(url).body(data);
            let request = self.add_auth_header(request);

            request
                .send()
                .await
                .map_err(|e| std::io::Error::other(format!("Failed to upload to WebDAV: {}", e)))?;

            Ok(())
        })
    }
}

impl Drop for WebDavWriter {
    fn drop(&mut self) {
        let _ = self.flush();
    }
}
