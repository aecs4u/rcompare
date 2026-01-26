// Example: Using RCompare with S3 and WebDAV cloud storage
//
// This example demonstrates how to use the S3Vfs and WebDavVfs implementations
// to compare files stored in cloud storage.

use rcompare_core::vfs::{S3Vfs, S3Config, S3Auth, WebDavVfs, WebDavConfig, WebDavAuth};
use rcompare_core::scanner::FolderScanner;
use rcompare_common::Vfs;
use std::path::PathBuf;
use std::io::Read;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("RCompare Cloud Storage Examples\n");

    // Example 1: Connect to AWS S3
    example_s3_default_credentials()?;

    // Example 2: Connect to MinIO (S3-compatible)
    example_minio()?;

    // Example 3: Connect to WebDAV (Nextcloud)
    example_nextcloud_webdav()?;

    // Example 4: Compare local directory with S3 bucket
    example_compare_local_to_s3()?;

    // Example 5: Sync WebDAV to local
    example_sync_webdav_to_local()?;

    Ok(())
}

/// Example 1: Connect to AWS S3 using default credentials
fn example_s3_default_credentials() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Example 1: AWS S3 with Default Credentials ===");

    let config = S3Config {
        bucket: "my-backup-bucket".to_string(),
        region: "us-east-1".to_string(),
        prefix: PathBuf::from("/documents"),
        auth: S3Auth::Default, // Uses AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars
        endpoint: None,
    };

    let vfs = S3Vfs::new(config)?;
    println!("Connected to S3: {}", vfs.instance_id());

    // List files in the root
    match vfs.read_dir(&PathBuf::from("/")) {
        Ok(entries) => {
            println!("Found {} entries:", entries.len());
            for entry in entries.iter().take(5) {
                println!("  - {}: {} bytes", entry.path.display(), entry.size);
            }
        }
        Err(e) => println!("Error listing S3 bucket: {:?}", e),
    }

    println!();
    Ok(())
}

/// Example 2: Connect to MinIO (S3-compatible storage)
fn example_minio() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Example 2: MinIO (S3-compatible) ===");

    let config = S3Config {
        bucket: "test-bucket".to_string(),
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
    println!("Connected to MinIO: {}", vfs.instance_id());

    // Write a test file
    let test_path = PathBuf::from("example.txt");
    let test_content = b"Hello from RCompare!";

    match vfs.write_file(&test_path, test_content) {
        Ok(_) => println!("Successfully wrote file: {}", test_path.display()),
        Err(e) => println!("Error writing file: {:?}", e),
    }

    // Read it back
    match vfs.open_file(&test_path) {
        Ok(mut reader) => {
            let mut contents = String::new();
            reader.read_to_string(&mut contents)?;
            println!("Read back: {}", contents);
        }
        Err(e) => println!("Error reading file: {:?}", e),
    }

    println!();
    Ok(())
}

/// Example 3: Connect to Nextcloud WebDAV
fn example_nextcloud_webdav() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Example 3: Nextcloud WebDAV ===");

    let config = WebDavConfig {
        url: "https://cloud.example.com/remote.php/dav/files/username".to_string(),
        auth: WebDavAuth::Basic {
            username: "username".to_string(),
            password: "app-password".to_string(), // Use app-specific password
        },
        root_path: PathBuf::from("/Documents"),
    };

    let vfs = WebDavVfs::new(config)?;
    println!("Connected to WebDAV: {}", vfs.instance_id());

    // List directory
    match vfs.read_dir(&PathBuf::from("/")) {
        Ok(entries) => {
            println!("Found {} entries:", entries.len());
            for entry in entries.iter().take(5) {
                let type_str = if entry.is_dir { "DIR " } else { "FILE" };
                println!("  [{}] {}", type_str, entry.path.display());
            }
        }
        Err(e) => println!("Error listing WebDAV directory: {:?}", e),
    }

    println!();
    Ok(())
}

/// Example 4: Compare local directory with S3 bucket
fn example_compare_local_to_s3() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Example 4: Compare Local to S3 ===");

    // Set up local VFS
    use rcompare_core::vfs::LocalVfs;
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

    println!("Scanning local directory...");
    let local_files = scanner.scan_vfs(&local_vfs, &PathBuf::from("/"))?;

    println!("Scanning S3 bucket...");
    let s3_files = scanner.scan_vfs(&s3_vfs, &PathBuf::from("/"))?;

    println!("Local: {} files", local_files.len());
    println!("S3: {} files", s3_files.len());

    // Find differences
    let mut missing_in_s3 = 0;
    let mut missing_locally = 0;

    for local_file in &local_files {
        if !s3_files.iter().any(|s3| s3.path == local_file.path) {
            missing_in_s3 += 1;
        }
    }

    for s3_file in &s3_files {
        if !local_files.iter().any(|local| local.path == s3_file.path) {
            missing_locally += 1;
        }
    }

    println!("Files missing in S3: {}", missing_in_s3);
    println!("Files missing locally: {}", missing_locally);

    println!();
    Ok(())
}

/// Example 5: Sync WebDAV to local
fn example_sync_webdav_to_local() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Example 5: Sync WebDAV to Local ===");

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
    use rcompare_core::vfs::LocalVfs;
    let dest = LocalVfs::new(PathBuf::from("/home/user/photo-backup"))?;

    // Get files to sync
    println!("Listing files on WebDAV...");
    let files = source.read_dir(&PathBuf::from("/"))?;
    println!("Found {} files to sync", files.len());

    let mut synced = 0;
    let mut failed = 0;

    for file in files {
        if !file.is_dir {
            // Read from WebDAV
            match source.open_file(&file.path) {
                Ok(mut reader) => {
                    let mut contents = Vec::new();
                    if let Err(e) = reader.read_to_end(&mut contents) {
                        println!("Error reading {}: {:?}", file.path.display(), e);
                        failed += 1;
                        continue;
                    }

                    // Write to local
                    match dest.write_file(&file.path, &contents) {
                        Ok(_) => {
                            println!("Synced: {}", file.path.display());
                            synced += 1;
                        }
                        Err(e) => {
                            println!("Error writing {}: {:?}", file.path.display(), e);
                            failed += 1;
                        }
                    }
                }
                Err(e) => {
                    println!("Error opening {}: {:?}", file.path.display(), e);
                    failed += 1;
                }
            }
        }
    }

    println!("Sync complete: {} synced, {} failed", synced, failed);

    println!();
    Ok(())
}

/// Example 6: Using DigitalOcean Spaces
#[allow(dead_code)]
fn example_digitalocean_spaces() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Example 6: DigitalOcean Spaces ===");

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
    println!("Connected to DigitalOcean Spaces: {}", vfs.instance_id());

    println!();
    Ok(())
}

/// Example 7: Using Apache WebDAV
#[allow(dead_code)]
fn example_apache_webdav() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Example 7: Apache mod_dav ===");

    let config = WebDavConfig {
        url: "http://localhost/webdav".to_string(),
        auth: WebDavAuth::Basic {
            username: "davuser".to_string(),
            password: "davpass".to_string(),
        },
        root_path: PathBuf::from("/"),
    };

    let vfs = WebDavVfs::new(config)?;
    println!("Connected to Apache WebDAV: {}", vfs.instance_id());

    // Create a directory
    let dir_path = PathBuf::from("test-directory");
    match vfs.create_dir(&dir_path) {
        Ok(_) => println!("Created directory: {}", dir_path.display()),
        Err(e) => println!("Error creating directory: {:?}", e),
    }

    println!();
    Ok(())
}
