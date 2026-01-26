use rcompare_common::{FileEntry, FileMetadata, Vfs, VfsError};
use ssh2::{Session, Sftp};
use std::io::{Cursor, Read};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, UNIX_EPOCH};

/// SFTP connection configuration
#[derive(Debug, Clone)]
pub struct SftpConfig {
    pub host: String,
    pub port: u16,
    pub username: String,
    pub auth: SftpAuth,
    pub root_path: PathBuf,
}

/// Authentication method for SFTP
#[derive(Debug, Clone)]
pub enum SftpAuth {
    Password(String),
    KeyFile {
        private_key: PathBuf,
        passphrase: Option<String>,
    },
    Agent,
}

impl Default for SftpConfig {
    fn default() -> Self {
        Self {
            host: "localhost".to_string(),
            port: 22,
            username: String::new(),
            auth: SftpAuth::Agent,
            root_path: PathBuf::from("/"),
        }
    }
}

/// SFTP Virtual File System implementation
pub struct SftpVfs {
    instance_id: String,
    config: SftpConfig,
    session: Mutex<Session>,
}

impl SftpVfs {
    /// Create a new SFTP VFS connection
    pub fn new(config: SftpConfig) -> Result<Self, VfsError> {
        let instance_id = format!("sftp://{}@{}:{}{}",
            config.username, config.host, config.port, config.root_path.display());

        let session = Self::connect(&config)?;

        Ok(Self {
            instance_id,
            config,
            session: Mutex::new(session),
        })
    }

    fn connect(config: &SftpConfig) -> Result<Session, VfsError> {
        let addr = format!("{}:{}", config.host, config.port);
        let tcp = TcpStream::connect(&addr)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::ConnectionRefused,
                format!("Failed to connect to {}: {}", addr, e)
            )))?;

        tcp.set_read_timeout(Some(Duration::from_secs(30)))
            .map_err(|e| VfsError::Io(e))?;
        tcp.set_write_timeout(Some(Duration::from_secs(30)))
            .map_err(|e| VfsError::Io(e))?;

        let mut session = Session::new()
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Failed to create SSH session: {}", e)
            )))?;

        session.set_tcp_stream(tcp);
        session.handshake()
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::ConnectionRefused,
                format!("SSH handshake failed: {}", e)
            )))?;

        // Authenticate
        match &config.auth {
            SftpAuth::Password(password) => {
                session.userauth_password(&config.username, password)
                    .map_err(|e| VfsError::Io(std::io::Error::new(
                        std::io::ErrorKind::PermissionDenied,
                        format!("Password authentication failed: {}", e)
                    )))?;
            }
            SftpAuth::KeyFile { private_key, passphrase } => {
                session.userauth_pubkey_file(
                    &config.username,
                    None,
                    private_key,
                    passphrase.as_deref(),
                ).map_err(|e| VfsError::Io(std::io::Error::new(
                    std::io::ErrorKind::PermissionDenied,
                    format!("Key file authentication failed: {}", e)
                )))?;
            }
            SftpAuth::Agent => {
                let mut agent = session.agent()
                    .map_err(|e| VfsError::Io(std::io::Error::new(
                        std::io::ErrorKind::Other,
                        format!("Failed to connect to SSH agent: {}", e)
                    )))?;

                agent.connect()
                    .map_err(|e| VfsError::Io(std::io::Error::new(
                        std::io::ErrorKind::Other,
                        format!("Failed to connect to SSH agent: {}", e)
                    )))?;

                agent.list_identities()
                    .map_err(|e| VfsError::Io(std::io::Error::new(
                        std::io::ErrorKind::Other,
                        format!("Failed to list SSH agent identities: {}", e)
                    )))?;

                let mut authenticated = false;
                for identity in agent.identities().unwrap_or_default() {
                    if agent.userauth(&config.username, &identity).is_ok() {
                        authenticated = true;
                        break;
                    }
                }

                if !authenticated {
                    return Err(VfsError::Io(std::io::Error::new(
                        std::io::ErrorKind::PermissionDenied,
                        "SSH agent authentication failed: no valid identity found"
                    )));
                }
            }
        }

        if !session.authenticated() {
            return Err(VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::PermissionDenied,
                "SSH authentication failed"
            )));
        }

        Ok(session)
    }

    fn get_sftp(&self) -> Result<Sftp, VfsError> {
        let session = self.session.lock()
            .map_err(|_| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                "Failed to lock session mutex"
            )))?;

        session.sftp()
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Failed to create SFTP channel: {}", e)
            )))
    }

    fn full_path(&self, path: &Path) -> PathBuf {
        self.config.root_path.join(path)
    }
}

impl Vfs for SftpVfs {
    fn instance_id(&self) -> &str {
        &self.instance_id
    }

    fn metadata(&self, path: &Path) -> Result<FileMetadata, VfsError> {
        let sftp = self.get_sftp()?;
        let full_path = self.full_path(path);

        let stat = sftp.stat(&full_path)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("Failed to stat {}: {}", full_path.display(), e)
            )))?;

        let modified = stat.mtime
            .map(|t| UNIX_EPOCH + Duration::from_secs(t))
            .unwrap_or(UNIX_EPOCH);

        Ok(FileMetadata {
            size: stat.size.unwrap_or(0),
            modified,
            is_dir: stat.is_dir(),
            is_symlink: stat.file_type().is_symlink(),
        })
    }

    fn read_dir(&self, path: &Path) -> Result<Vec<FileEntry>, VfsError> {
        let sftp = self.get_sftp()?;
        let full_path = self.full_path(path);

        let entries = sftp.readdir(&full_path)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("Failed to read directory {}: {}", full_path.display(), e)
            )))?;

        let file_entries: Vec<FileEntry> = entries
            .into_iter()
            .filter_map(|(entry_path, stat)| {
                // Get the relative path from the root
                let rel_path = entry_path.strip_prefix(&self.config.root_path)
                    .ok()?
                    .to_path_buf();

                // Skip . and ..
                let name = rel_path.file_name()?.to_str()?;
                if name == "." || name == ".." {
                    return None;
                }

                let modified = stat.mtime
                    .map(|t| UNIX_EPOCH + Duration::from_secs(t))
                    .unwrap_or(UNIX_EPOCH);

                Some(FileEntry {
                    path: rel_path,
                    size: stat.size.unwrap_or(0),
                    modified,
                    is_dir: stat.is_dir(),
                })
            })
            .collect();

        Ok(file_entries)
    }

    fn open_file(&self, path: &Path) -> Result<Box<dyn Read + Send>, VfsError> {
        let sftp = self.get_sftp()?;
        let full_path = self.full_path(path);

        let mut file = sftp.open(&full_path)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("Failed to open {}: {}", full_path.display(), e)
            )))?;

        // Read entire file into memory (SFTP files don't implement Send)
        let mut contents = Vec::new();
        file.read_to_end(&mut contents)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Failed to read {}: {}", full_path.display(), e)
            )))?;

        Ok(Box::new(Cursor::new(contents)))
    }

    fn remove_file(&self, path: &Path) -> Result<(), VfsError> {
        let sftp = self.get_sftp()?;
        let full_path = self.full_path(path);

        sftp.unlink(&full_path)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Failed to remove {}: {}", full_path.display(), e)
            )))?;

        Ok(())
    }

    fn copy_file(&self, src: &Path, dest: &Path) -> Result<(), VfsError> {
        // SFTP doesn't have a native copy, so we read and write
        let sftp = self.get_sftp()?;
        let src_full = self.full_path(src);
        let dest_full = self.full_path(dest);

        // Read source file
        let mut src_file = sftp.open(&src_full)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("Failed to open source {}: {}", src_full.display(), e)
            )))?;

        let mut contents = Vec::new();
        src_file.read_to_end(&mut contents)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Failed to read source {}: {}", src_full.display(), e)
            )))?;

        // Write to destination
        let mut dest_file = sftp.create(&dest_full)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Failed to create destination {}: {}", dest_full.display(), e)
            )))?;

        std::io::Write::write_all(&mut dest_file, &contents)
            .map_err(|e| VfsError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("Failed to write destination {}: {}", dest_full.display(), e)
            )))?;

        Ok(())
    }
}

// Note: We can't easily test SFTP without a real server,
// so tests would require integration testing with a mock server or real SSH server
