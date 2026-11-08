use super::remote_reader::{create_spool_file, open_spool_reader};
use quick_xml::events::Event;
use quick_xml::Reader as XmlReader;
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
        if matches!(config.auth, WebDavAuth::Digest { .. }) {
            return Err(VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "WebDAV Digest authentication is not supported",
            )));
        }
        let instance_id = format!("webdav://{}{}", config.url, config.root_path.display());

        // Parse base URL
        let mut base_url = Url::parse(&config.url).map_err(|e| {
            VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                format!("Invalid WebDAV URL: {e}"),
            ))
        })?;
        if !base_url.path().ends_with('/') {
            let path = format!("{}/", base_url.path());
            base_url.set_path(&path);
        }

        // Create a Tokio runtime for async operations
        let runtime = Runtime::new().map_err(|e| {
            VfsError::Io(std::io::Error::other(format!(
                "Failed to create async runtime: {e}"
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
                "Failed to create HTTP client: {e}"
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
                format!("Failed to construct WebDAV URL: {e}"),
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
                let _ = (username, password);
                builder
            }
            WebDavAuth::Bearer { token } => {
                builder.header("Authorization", format!("Bearer {token}"))
            }
        }
    }

    fn parse_propfind_response(
        &self,
        xml: &str,
        path: &Path,
        skip_parent: bool,
    ) -> Result<Vec<FileEntry>, VfsError> {
        let mut reader = XmlReader::from_str(xml);
        let mut entries = Vec::new();
        let mut current: Option<ParsedPropfindEntry> = None;
        let mut field: Option<Vec<u8>> = None;

        loop {
            match reader.read_event() {
                Ok(Event::Start(event)) => {
                    let event_name = event.name();
                    let name = local_name(event_name.as_ref());
                    if name == b"response" {
                        current = Some(ParsedPropfindEntry::default());
                    } else if matches!(
                        name,
                        b"href" | b"getcontentlength" | b"getlastmodified" | b"creationdate"
                    ) {
                        field = Some(name.to_vec());
                    } else if name == b"collection" {
                        if let Some(entry) = current.as_mut() {
                            entry.is_dir = true;
                        }
                    }
                }
                Ok(Event::Empty(event)) => {
                    if local_name(event.name().as_ref()) == b"collection" {
                        if let Some(entry) = current.as_mut() {
                            entry.is_dir = true;
                        }
                    }
                }
                Ok(Event::Text(text)) => {
                    if let (Some(entry), Some(name)) = (current.as_mut(), field.as_deref()) {
                        let decoded = text.decode().map_err(|e| xml_error(e.to_string()))?;
                        let value = quick_xml::escape::unescape(&decoded)
                            .map_err(|e| xml_error(e.to_string()))?;
                        match name {
                            b"href" => entry.href = Some(value.into_owned()),
                            b"getcontentlength" => entry.size = value.parse().unwrap_or(0),
                            b"getlastmodified" | b"creationdate" => {
                                entry.modified = Self::parse_date(&value);
                            }
                            _ => {}
                        }
                    }
                }
                Ok(Event::End(event)) => {
                    let event_name = event.name();
                    let name = local_name(event_name.as_ref());
                    if matches!(
                        name,
                        b"href" | b"getcontentlength" | b"getlastmodified" | b"creationdate"
                    ) {
                        field = None;
                    } else if name == b"response" {
                        if let Some(entry) = current.take() {
                            if let Some(href) = entry.href {
                                let entry_path = self.href_to_path(&href);
                                let requested = normalize_path(path);
                                if !skip_parent || entry_path != requested {
                                    entries.push(FileEntry {
                                        path: entry_path,
                                        size: entry.size,
                                        modified: entry.modified.unwrap_or(UNIX_EPOCH),
                                        is_dir: entry.is_dir || href.ends_with('/'),
                                    });
                                }
                            }
                        }
                    }
                }
                Ok(Event::Eof) => break,
                Ok(_) => {}
                Err(e) => return Err(xml_error(e.to_string())),
            }
        }

        Ok(entries)
    }

    fn href_to_path(&self, href: &str) -> PathBuf {
        let href_path = Url::parse(href).map_or_else(
            |_| href.split('?').next().unwrap_or(href).to_string(),
            |url| url.path().to_string(),
        );
        let base_path = format!(
            "{}/{}",
            self.base_url.path().trim_end_matches('/'),
            self.config.root_path.to_string_lossy().trim_matches('/')
        );
        let relative = href_path
            .strip_prefix(base_path.trim_end_matches('/'))
            .unwrap_or(href_path.as_str())
            .trim_matches('/');
        PathBuf::from(relative)
    }

    fn parse_date(date_str: &str) -> Option<SystemTime> {
        chrono::DateTime::parse_from_rfc3339(date_str)
            .ok()
            .map(|date| date.into())
            .or_else(|| httpdate::parse_http_date(date_str).ok())
    }
}

#[derive(Default)]
struct ParsedPropfindEntry {
    href: Option<String>,
    size: u64,
    modified: Option<SystemTime>,
    is_dir: bool,
}

const UNIX_EPOCH: SystemTime = SystemTime::UNIX_EPOCH;

fn local_name(name: &[u8]) -> &[u8] {
    name.rsplit(|byte| *byte == b':').next().unwrap_or(name)
}

fn normalize_path(path: &Path) -> PathBuf {
    PathBuf::from(path.to_string_lossy().replace('\\', "/").trim_matches('/'))
}

fn xml_error(message: String) -> VfsError {
    VfsError::Io(std::io::Error::new(
        std::io::ErrorKind::InvalidData,
        format!("Invalid WebDAV XML: {message}"),
    ))
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
                    "WebDAV PROPFIND failed: {e}"
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
                    "Failed to read PROPFIND response: {e}"
                )))
            })?;

            let mut entries = self.parse_propfind_response(&xml, path, false)?;
            let entry = entries.pop().ok_or_else(|| {
                VfsError::NotFound(format!("WebDAV resource not found: {}", path.display()))
            })?;

            Ok(FileMetadata {
                size: entry.size,
                modified: entry.modified,
                is_dir: entry.is_dir,
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
                    "WebDAV PROPFIND failed: {e}"
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
                    "Failed to read PROPFIND response: {e}"
                )))
            })?;

            self.parse_propfind_response(&xml, path, true)
        })
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let request = self.client.get(url);
            let request = self.add_auth_header(request);

            let mut response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::new(
                    std::io::ErrorKind::NotFound,
                    format!("Failed to GET WebDAV file: {e}"),
                ))
            })?;

            if !response.status().is_success() {
                return Err(VfsError::NotFound(format!(
                    "WebDAV file not found: {}",
                    path.display()
                )));
            }

            let (spool_path, mut spool) = create_spool_file().map_err(VfsError::Io)?;
            let result = async {
                while let Some(chunk) = response.chunk().await.map_err(|e| {
                    VfsError::Io(std::io::Error::other(format!(
                        "Failed to read WebDAV file body: {e}"
                    )))
                })? {
                    spool.write_all(&chunk).map_err(VfsError::Io)?;
                }
                spool.sync_all().map_err(VfsError::Io)
            }
            .await;

            drop(spool);
            if let Err(error) = result {
                let _ = std::fs::remove_file(&spool_path);
                return Err(error);
            }

            open_spool_reader(spool_path).map_err(VfsError::Io)
        })
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        let url = self.to_webdav_url(path)?;

        self.runtime.block_on(async {
            let request = self.client.delete(url);
            let request = self.add_auth_header(request);

            let response = request.send().await.map_err(|e| {
                VfsError::Io(std::io::Error::other(format!(
                    "Failed to DELETE WebDAV resource: {e}"
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

    fn remove_dir(&self, path: &Path) -> Result<(), VfsError> {
        self.remove_file(path)
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
                    "Failed to COPY WebDAV resource: {e}"
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
                    "Failed to MKCOL WebDAV directory: {e}"
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
                    "Failed to MOVE WebDAV resource: {e}"
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
                    "Failed to PUT WebDAV file: {e}"
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
    dirty: bool,
}

impl WebDavWriter {
    fn new(client: Arc<Client>, runtime: Arc<Runtime>, url: Url, auth: WebDavAuth) -> Self {
        Self {
            client,
            runtime,
            url,
            auth,
            buffer: Vec::new(),
            dirty: true,
        }
    }

    fn add_auth_header(&self, builder: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
        match &self.auth {
            WebDavAuth::None => builder,
            WebDavAuth::Basic { username, password } => {
                builder.basic_auth(username, Some(password))
            }
            WebDavAuth::Digest { username, password } => {
                let _ = (username, password);
                builder
            }
            WebDavAuth::Bearer { token } => {
                builder.header("Authorization", format!("Bearer {token}"))
            }
        }
    }
}

impl std::io::Write for WebDavWriter {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.buffer.extend_from_slice(buf);
        self.dirty = true;
        Ok(buf.len())
    }

    fn flush(&mut self) -> std::io::Result<()> {
        if !self.dirty {
            return Ok(());
        }
        // Upload the buffer to WebDAV
        let client = self.client.clone();
        let url = self.url.clone();
        let data = self.buffer.clone();

        self.runtime.block_on(async {
            let request = client.put(url).body(data);
            let request = self.add_auth_header(request);

            let response = request
                .send()
                .await
                .map_err(|e| std::io::Error::other(format!("Failed to upload to WebDAV: {e}")))?;

            if !response.status().is_success() {
                return Err(std::io::Error::other(format!(
                    "WebDAV PUT returned status: {}",
                    response.status()
                )));
            }

            Ok(())
        })?;
        self.buffer.clear();
        self.dirty = false;
        Ok(())
    }
}

impl Drop for WebDavWriter {
    fn drop(&mut self) {
        let _ = self.flush();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_namespaced_propfind_entries_and_metadata() {
        let vfs = WebDavVfs::new(WebDavConfig {
            url: "https://example.test/dav".to_string(),
            auth: WebDavAuth::None,
            root_path: PathBuf::from("/Documents"),
        })
        .expect("valid WebDAV config");
        let xml = r#"
            <d:multistatus xmlns:d="DAV:">
              <d:response>
                <d:href>/dav/Documents/report.txt</d:href>
                <d:propstat><d:prop>
                  <d:getcontentlength>42</d:getcontentlength>
                  <d:getlastmodified>Tue, 15 Nov 1994 12:45:26 GMT</d:getlastmodified>
                  <d:resourcetype/>
                </d:prop></d:propstat>
              </d:response>
              <d:response>
                <d:href>/dav/Documents/subdir/</d:href>
                <d:propstat><d:prop>
                  <d:resourcetype><d:collection/></d:resourcetype>
                </d:prop></d:propstat>
              </d:response>
            </d:multistatus>
        "#;

        let entries = vfs
            .parse_propfind_response(xml, Path::new("Documents"), true)
            .expect("valid PROPFIND XML");
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].path, PathBuf::from("report.txt"));
        assert_eq!(entries[0].size, 42);
        assert!(!entries[0].is_dir);
        assert_eq!(entries[1].path, PathBuf::from("subdir"));
        assert!(entries[1].is_dir);
        assert_ne!(entries[0].modified, UNIX_EPOCH);
    }

    #[test]
    fn digest_auth_is_rejected_instead_of_downgraded() {
        let result = WebDavVfs::new(WebDavConfig {
            url: "https://example.test/dav".to_string(),
            auth: WebDavAuth::Digest {
                username: "user".to_string(),
                password: "secret".to_string(),
            },
            root_path: PathBuf::from("/"),
        });
        assert!(result.is_err());
    }
}
