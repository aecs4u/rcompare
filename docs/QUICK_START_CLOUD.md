# Quick Start: Cloud Storage in RCompare

This guide provides quick examples to get started with S3 and WebDAV cloud storage in RCompare.

## S3 Quick Start

### Example 1: Connect to AWS S3 (Default Credentials)

```rust
use rcompare_core::vfs::{S3Vfs, S3Config, S3Auth};
use rcompare_common::Vfs;
use std::path::PathBuf;

// Configure S3 connection
let config = S3Config {
    bucket: "my-bucket".to_string(),
    region: "us-east-1".to_string(),
    prefix: PathBuf::from("/"),
    auth: S3Auth::Default, // Uses AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
    endpoint: None,
};

// Connect
let vfs = S3Vfs::new(config)?;

// List files
let files = vfs.read_dir(&PathBuf::from("/"))?;
for file in files {
    println!("{}", file.path.display());
}
```

### Example 2: Connect to MinIO

```rust
let config = S3Config {
    bucket: "my-bucket".to_string(),
    region: "us-east-1".to_string(),
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

### Example 3: Read and Write Files

```rust
use std::io::{Read, Write};

// Write a file
vfs.write_file(&PathBuf::from("test.txt"), b"Hello, S3!")?;

// Read a file
let mut reader = vfs.open_file(&PathBuf::from("test.txt"))?;
let mut contents = String::new();
reader.read_to_string(&mut contents)?;
println!("Contents: {}", contents);
```

## WebDAV Quick Start

### Example 1: Connect to Nextcloud

```rust
use rcompare_core::vfs::{WebDavVfs, WebDavConfig, WebDavAuth};
use rcompare_common::Vfs;
use std::path::PathBuf;

let config = WebDavConfig {
    url: "https://cloud.example.com/remote.php/dav/files/username".to_string(),
    auth: WebDavAuth::Basic {
        username: "username".to_string(),
        password: "app-password".to_string(), // Use app password!
    },
    root_path: PathBuf::from("/Documents"),
};

let vfs = WebDavVfs::new(config)?;

// List directory
let files = vfs.read_dir(&PathBuf::from("/"))?;
for file in files {
    println!("{}", file.path.display());
}
```

### Example 2: Upload a File

```rust
// Read local file
let local_content = std::fs::read("local-file.txt")?;

// Upload to WebDAV
vfs.write_file(&PathBuf::from("remote-file.txt"), &local_content)?;

println!("File uploaded successfully!");
```

### Example 3: Create Directory

```rust
vfs.create_dir(&PathBuf::from("NewFolder"))?;
println!("Directory created!");
```

## Environment Variables

### For AWS S3

```bash
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_DEFAULT_REGION=us-east-1
```

### For S3-Compatible Services

```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_ENDPOINT_URL=http://localhost:9000  # MinIO example
```

## Common Operations

### Copy Files Between Cloud and Local

```rust
use rcompare_core::vfs::LocalVfs;

// Source: S3
let s3_vfs = S3Vfs::new(s3_config)?;

// Destination: Local
let local_vfs = LocalVfs::new(PathBuf::from("/home/user/backup"))?;

// Copy file
let mut reader = s3_vfs.open_file(&PathBuf::from("file.txt"))?;
let mut contents = Vec::new();
reader.read_to_end(&mut contents)?;
local_vfs.write_file(&PathBuf::from("file.txt"), &contents)?;
```

### Compare Local and Cloud

```rust
use rcompare_core::scanner::FolderScanner;

let scanner = FolderScanner::new();

// Scan local
let local_vfs = LocalVfs::new(PathBuf::from("/home/user/data"))?;
let local_files = scanner.scan_vfs(&local_vfs, &PathBuf::from("/"))?;

// Scan S3
let s3_vfs = S3Vfs::new(s3_config)?;
let s3_files = scanner.scan_vfs(&s3_vfs, &PathBuf::from("/"))?;

// Compare
println!("Local: {} files", local_files.len());
println!("S3: {} files", s3_files.len());
```

## Supported Cloud Providers

### S3-Compatible
- ✅ Amazon S3 (AWS)
- ✅ MinIO
- ✅ DigitalOcean Spaces
- ✅ Wasabi
- ✅ Backblaze B2 (S3 API)
- ✅ Cloudflare R2

### WebDAV
- ✅ Nextcloud
- ✅ ownCloud
- ✅ Apache mod_dav
- ✅ Nginx WebDAV module
- ✅ Box.com (WebDAV enabled)

## Troubleshooting

### S3: Connection Refused
- Check internet connectivity
- Verify region is correct
- For MinIO, ensure endpoint URL is correct

### S3: Access Denied
- Verify credentials
- Check IAM permissions (need `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`)

### WebDAV: 401 Unauthorized
- Verify username/password
- For Nextcloud/ownCloud, use app-specific password
- Check two-factor authentication settings

### WebDAV: SSL Error
- Ensure valid SSL certificate
- Use HTTPS for production

## Next Steps

- Read the full [Cloud Storage Guide](CLOUD_STORAGE.md)
- Check out [Examples](../examples/cloud_storage_example.rs)
- Review the [Architecture Documentation](../ARCHITECTURE.md)

## Getting Help

- GitHub Issues: https://github.com/aecs4u/rcompare/issues
- Documentation: https://github.com/aecs4u/rcompare/tree/main/docs
