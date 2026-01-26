# Cloud Storage Support in RCompare

RCompare v2.0+ provides native support for cloud storage backends through its Virtual File System (VFS) abstraction. This document explains how to use S3 and WebDAV storage with RCompare.

## Table of Contents

- [S3 Storage Support](#s3-storage-support)
- [WebDAV Storage Support](#webdav-storage-support)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## S3 Storage Support

RCompare supports Amazon S3 and S3-compatible storage services (MinIO, DigitalOcean Spaces, Wasabi, etc.).

### Features

- ✅ List objects in buckets
- ✅ Read/write files
- ✅ Copy files within the same bucket
- ✅ Delete files
- ✅ Create directories (as folder markers)
- ✅ Multiple authentication methods
- ✅ Custom endpoint support for S3-compatible services
- ⚠️ No modification time setting (S3 limitation)

### Authentication Methods

#### 1. Default Credential Chain (Recommended for AWS)

Uses the standard AWS credential resolution:
1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. AWS credentials file (`~/.aws/credentials`)
3. IAM role (when running on EC2/ECS/Lambda)

```rust
use rcompare_core::vfs::{S3Vfs, S3Config, S3Auth};
use std::path::PathBuf;

let config = S3Config {
    bucket: "my-bucket".to_string(),
    region: "us-east-1".to_string(),
    prefix: PathBuf::from("/data"),
    auth: S3Auth::Default,
    endpoint: None,
};

let vfs = S3Vfs::new(config)?;
```

#### 2. Explicit Access Keys

Useful for testing or when credentials aren't in the standard locations:

```rust
let config = S3Config {
    bucket: "my-bucket".to_string(),
    region: "us-west-2".to_string(),
    prefix: PathBuf::from("/"),
    auth: S3Auth::AccessKey {
        access_key_id: "AKIAIOSFODNN7EXAMPLE".to_string(),
        secret_access_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY".to_string(),
        session_token: None, // Optional for temporary credentials
    },
    endpoint: None,
};

let vfs = S3Vfs::new(config)?;
```

#### 3. Anonymous Access (Public Buckets)

For public S3 buckets that don't require authentication:

```rust
let config = S3Config {
    bucket: "public-data-bucket".to_string(),
    region: "us-east-1".to_string(),
    prefix: PathBuf::from("/"),
    auth: S3Auth::Anonymous,
    endpoint: None,
};

let vfs = S3Vfs::new(config)?;
```

### S3-Compatible Services

RCompare works with any S3-compatible service by specifying a custom endpoint:

#### MinIO Example

```rust
let config = S3Config {
    bucket: "my-bucket".to_string(),
    region: "us-east-1".to_string(), // MinIO ignores this
    prefix: PathBuf::from("/"),
    auth: S3Auth::AccessKey {
        access_key_id: "minioadmin".to_string(),
        secret_access_key: "minioadmin".to_string(),
        session_token: None,
    },
    endpoint: Some("http://localhost:9000".to_string()),
};

let vfs = S3Vfs::new(config)?;
```

#### DigitalOcean Spaces Example

```rust
let config = S3Config {
    bucket: "my-space".to_string(),
    region: "nyc3".to_string(),
    prefix: PathBuf::from("/"),
    auth: S3Auth::AccessKey {
        access_key_id: "YOUR_SPACES_KEY".to_string(),
        secret_access_key: "YOUR_SPACES_SECRET".to_string(),
        session_token: None,
    },
    endpoint: Some("https://nyc3.digitaloceanspaces.com".to_string()),
};

let vfs = S3Vfs::new(config)?;
```

#### Wasabi Example

```rust
let config = S3Config {
    bucket: "my-bucket".to_string(),
    region: "us-west-1".to_string(),
    prefix: PathBuf::from("/"),
    auth: S3Auth::AccessKey {
        access_key_id: "YOUR_WASABI_KEY".to_string(),
        secret_access_key: "YOUR_WASABI_SECRET".to_string(),
        session_token: None,
    },
    endpoint: Some("https://s3.us-west-1.wasabisys.com".to_string()),
};

let vfs = S3Vfs::new(config)?;
```

### Basic Operations

```rust
use rcompare_common::Vfs;
use std::io::{Read, Write};
use std::path::PathBuf;

// List files
let entries = vfs.read_dir(&PathBuf::from("/documents"))?;
for entry in entries {
    println!("{}: {} bytes", entry.path.display(), entry.size);
}

// Read a file
let mut reader = vfs.open_file(&PathBuf::from("/data/file.txt"))?;
let mut contents = String::new();
reader.read_to_string(&mut contents)?;

// Write a file
vfs.write_file(&PathBuf::from("/output/result.txt"), b"Hello, S3!")?;

// Get metadata
let metadata = vfs.metadata(&PathBuf::from("/data/file.txt"))?;
println!("Size: {}, Modified: {:?}", metadata.size, metadata.modified);

// Copy a file
vfs.copy_file(
    &PathBuf::from("/source.txt"),
    &PathBuf::from("/backup/source.txt")
)?;

// Delete a file
vfs.remove_file(&PathBuf::from("/temp/old-file.txt"))?;
```

---

## WebDAV Storage Support

RCompare supports WebDAV servers including Nextcloud, ownCloud, Apache mod_dav, and others.

### Features

- ✅ List directory contents (PROPFIND)
- ✅ Read/write files (GET/PUT)
- ✅ Copy files (COPY)
- ✅ Move/rename files (MOVE)
- ✅ Delete files (DELETE)
- ✅ Create directories (MKCOL)
- ✅ Multiple authentication methods
- ⚠️ No modification time setting (most WebDAV servers)

### Authentication Methods

#### 1. No Authentication

For public WebDAV servers or when authentication is handled by network layer:

```rust
use rcompare_core::vfs::{WebDavVfs, WebDavConfig, WebDavAuth};
use std::path::PathBuf;

let config = WebDavConfig {
    url: "http://localhost:8080/webdav".to_string(),
    auth: WebDavAuth::None,
    root_path: PathBuf::from("/"),
};

let vfs = WebDavVfs::new(config)?;
```

#### 2. HTTP Basic Authentication

Most common authentication method for WebDAV:

```rust
let config = WebDavConfig {
    url: "https://cloud.example.com/remote.php/dav/files/username".to_string(),
    auth: WebDavAuth::Basic {
        username: "username".to_string(),
        password: "app-password".to_string(),
    },
    root_path: PathBuf::from("/"),
};

let vfs = WebDavVfs::new(config)?;
```

#### 3. HTTP Digest Authentication

For servers requiring digest authentication:

```rust
let config = WebDavConfig {
    url: "https://webdav.example.com".to_string(),
    auth: WebDavAuth::Digest {
        username: "user".to_string(),
        password: "password".to_string(),
    },
    root_path: PathBuf::from("/"),
};

let vfs = WebDavVfs::new(config)?;
```

**Note:** Current implementation uses Basic auth as a fallback for Digest. Full digest auth support is planned.

#### 4. Bearer Token Authentication

For OAuth2 or token-based authentication:

```rust
let config = WebDavConfig {
    url: "https://api.example.com/webdav".to_string(),
    auth: WebDavAuth::Bearer {
        token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...".to_string(),
    },
    root_path: PathBuf::from("/"),
};

let vfs = WebDavVfs::new(config)?;
```

### WebDAV Server Examples

#### Nextcloud

```rust
let config = WebDavConfig {
    url: "https://cloud.example.com/remote.php/dav/files/myusername".to_string(),
    auth: WebDavAuth::Basic {
        username: "myusername".to_string(),
        password: "app-password-here".to_string(), // Use app password, not main password
    },
    root_path: PathBuf::from("/Documents"),
};

let vfs = WebDavVfs::new(config)?;
```

**Tip:** Generate an app-specific password in Nextcloud settings for better security.

#### ownCloud

```rust
let config = WebDavConfig {
    url: "https://owncloud.example.com/remote.php/webdav".to_string(),
    auth: WebDavAuth::Basic {
        username: "username".to_string(),
        password: "password".to_string(),
    },
    root_path: PathBuf::from("/"),
};

let vfs = WebDavVfs::new(config)?;
```

#### Apache mod_dav

```rust
let config = WebDavConfig {
    url: "http://localhost/webdav".to_string(),
    auth: WebDavAuth::Basic {
        username: "davuser".to_string(),
        password: "davpass".to_string(),
    },
    root_path: PathBuf::from("/"),
};

let vfs = WebDavVfs::new(config)?;
```

### Basic Operations

```rust
use rcompare_common::Vfs;
use std::io::Read;
use std::path::PathBuf;

// List directory
let entries = vfs.read_dir(&PathBuf::from("/Documents"))?;
for entry in entries {
    let type_str = if entry.is_dir { "DIR" } else { "FILE" };
    println!("[{}] {}", type_str, entry.path.display());
}

// Read a file
let mut reader = vfs.open_file(&PathBuf::from("/notes.txt"))?;
let mut contents = String::new();
reader.read_to_string(&mut contents)?;

// Write a file
vfs.write_file(&PathBuf::from("/new-file.txt"), b"Hello, WebDAV!")?;

// Create a directory
vfs.create_dir(&PathBuf::from("/NewFolder"))?;

// Copy a file
vfs.copy_file(
    &PathBuf::from("/document.pdf"),
    &PathBuf::from("/backup/document.pdf")
)?;

// Rename/move a file
vfs.rename(
    &PathBuf::from("/old-name.txt"),
    &PathBuf::from("/new-name.txt")
)?;

// Delete a file
vfs.remove_file(&PathBuf::from("/temporary.txt"))?;
```

---

## Usage Examples

### Comparing Local and S3 Directories

```rust
use rcompare_core::vfs::{LocalVfs, S3Vfs, S3Config, S3Auth};
use rcompare_core::scanner::FolderScanner;
use std::path::PathBuf;

// Set up local VFS
let local_vfs = LocalVfs::new(PathBuf::from("/home/user/documents"))?;

// Set up S3 VFS
let s3_config = S3Config {
    bucket: "backup-bucket".to_string(),
    region: "us-east-1".to_string(),
    prefix: PathBuf::from("/documents"),
    auth: S3Auth::Default,
    endpoint: None,
};
let s3_vfs = S3Vfs::new(s3_config)?;

// Scan both
let scanner = FolderScanner::new();
let local_files = scanner.scan_vfs(&local_vfs, &PathBuf::from("/"))?;
let s3_files = scanner.scan_vfs(&s3_vfs, &PathBuf::from("/"))?;

println!("Local: {} files", local_files.len());
println!("S3: {} files", s3_files.len());
```

### Syncing WebDAV to Local

```rust
use rcompare_core::vfs::{LocalVfs, WebDavVfs, WebDavConfig, WebDavAuth};
use rcompare_common::Vfs;
use std::path::PathBuf;
use std::io::{Read, Write};

// Source: WebDAV
let webdav_config = WebDavConfig {
    url: "https://cloud.example.com/remote.php/dav/files/user".to_string(),
    auth: WebDavAuth::Basic {
        username: "user".to_string(),
        password: "app-password".to_string(),
    },
    root_path: PathBuf::from("/Photos"),
};
let source = WebDavVfs::new(webdav_config)?;

// Destination: Local
let dest = LocalVfs::new(PathBuf::from("/home/user/photo-backup"))?;

// Sync files
let files = source.read_dir(&PathBuf::from("/"))?;
for file in files {
    if !file.is_dir {
        // Read from WebDAV
        let mut reader = source.open_file(&file.path)?;
        let mut contents = Vec::new();
        reader.read_to_end(&mut contents)?;

        // Write to local
        dest.write_file(&file.path, &contents)?;
        println!("Synced: {}", file.path.display());
    }
}
```

### Using FilteredVfs with Cloud Storage

```rust
use rcompare_core::vfs::{S3Vfs, FilteredVfs, S3Config, S3Auth};
use std::path::PathBuf;

// Base S3 VFS
let s3_config = S3Config {
    bucket: "project-data".to_string(),
    region: "eu-west-1".to_string(),
    prefix: PathBuf::from("/"),
    auth: S3Auth::Default,
    endpoint: None,
};
let s3_vfs = S3Vfs::new(s3_config)?;

// Wrap with filter to exclude temporary files
let filtered = FilteredVfs::new(
    Box::new(s3_vfs),
    vec!["*.txt".to_string(), "*.pdf".to_string()], // Include
    vec!["*.tmp".to_string(), ".git/**".to_string()], // Exclude
)?;

// Now operations only see .txt and .pdf files, excluding .tmp and .git
let entries = filtered.read_dir(&PathBuf::from("/"))?;
```

---

## Configuration

### Environment Variables for S3

```bash
# AWS credentials
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_DEFAULT_REGION=us-east-1

# For S3-compatible services
export AWS_ENDPOINT_URL=http://localhost:9000
```

### AWS Credentials File

Create `~/.aws/credentials`:

```ini
[default]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

[production]
aws_access_key_id = AKIAI44QH8DHBEXAMPLE
aws_secret_access_key = je7MtGbClwBF/2Zp9Utk/h3yCo8nvbEXAMPLEKEY
```

And `~/.aws/config`:

```ini
[default]
region = us-east-1
output = json

[profile production]
region = eu-west-1
output = json
```

---

## Troubleshooting

### S3 Issues

#### Connection Errors

```
Error: Failed to connect to S3
```

**Solution:**
- Check internet connectivity
- Verify the region is correct
- For S3-compatible services, ensure endpoint URL is correct
- Check firewall settings

#### Authentication Errors

```
Error: Access Denied
```

**Solution:**
- Verify access key and secret key are correct
- Check IAM permissions (need `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`)
- For IAM roles, ensure the role is attached to the EC2 instance

#### Bucket Not Found

```
Error: NoSuchBucket
```

**Solution:**
- Verify bucket name is correct (case-sensitive)
- Ensure bucket exists in the specified region
- Check you have permission to access the bucket

### WebDAV Issues

#### Connection Errors

```
Error: WebDAV PROPFIND failed
```

**Solution:**
- Verify the WebDAV URL is correct
- Check if server requires HTTPS
- Ensure WebDAV is enabled on the server
- Test with a WebDAV client like Cyberduck

#### Authentication Errors

```
Error: WebDAV returned status: 401 Unauthorized
```

**Solution:**
- Verify username and password
- For Nextcloud/ownCloud, use app-specific passwords
- Check if two-factor authentication is interfering

#### SSL Certificate Errors

```
Error: SSL certificate verification failed
```

**Solution:**
- Ensure server has valid SSL certificate
- For self-signed certificates, you may need to configure trust (not recommended for production)

### Performance Optimization

#### Slow Listing Operations

Cloud storage listing can be slow for large directories.

**Solutions:**
- Use prefix filters to limit scope
- Enable caching in RCompare settings
- Consider using parallel operations

#### Large File Transfers

**Solutions:**
- Ensure stable internet connection
- Consider using resumable uploads (planned feature)
- Monitor network bandwidth

---

## Feature Comparison

| Feature | S3Vfs | WebDavVfs | LocalVfs | SftpVfs |
|---------|-------|-----------|----------|---------|
| Read files | ✅ | ✅ | ✅ | ✅ |
| Write files | ✅ | ✅ | ✅ | ✅ |
| Delete files | ✅ | ✅ | ✅ | ✅ |
| Copy files | ✅ | ✅ | ✅ | ❌ |
| Rename files | ✅ | ✅ | ✅ | ❌ |
| Create directories | ✅ | ✅ | ✅ | ✅ |
| Set mtime | ❌ | ❌ | ✅ | ✅ |
| Streaming | ❌ | ❌ | ✅ | ✅ |
| Async operations | ✅ | ✅ | ❌ | ❌ |

---

## Future Enhancements

### Planned Features

- **Multipart uploads** for large files to S3
- **Streaming support** to reduce memory usage
- **Retry logic** with exponential backoff
- **Connection pooling** for better performance
- **Cache layer** for metadata
- **Full Digest authentication** for WebDAV
- **Google Drive** support
- **Dropbox** support
- **Azure Blob Storage** support

### Performance Improvements

- Parallel file operations
- Chunked transfers
- Compression support
- Delta sync algorithms

---

## Security Best Practices

1. **Never hardcode credentials** in source code
2. **Use environment variables** or credential files
3. **Enable HTTPS** for all connections
4. **Use IAM roles** when running on AWS infrastructure
5. **Generate app-specific passwords** for WebDAV services
6. **Rotate credentials** regularly
7. **Use least-privilege access** - only grant necessary permissions
8. **Enable encryption at rest** on S3 buckets
9. **Monitor access logs** for unusual activity
10. **Use VPC endpoints** for S3 when running on AWS

---

## Additional Resources

- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [WebDAV RFC 4918](https://tools.ietf.org/html/rfc4918)
- [Nextcloud WebDAV Documentation](https://docs.nextcloud.com/server/latest/user_manual/en/files/access_webdav.html)
- [RCompare VFS Architecture](../ARCHITECTURE.md#virtual-file-system-vfs-layer)
- [RCompare Examples](../examples/)

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/aecs4u/rcompare/issues
- Documentation: https://github.com/aecs4u/rcompare/tree/main/docs
- Examples: https://github.com/aecs4u/rcompare/tree/main/examples
