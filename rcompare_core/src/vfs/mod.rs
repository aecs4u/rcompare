pub mod archive;
pub mod local;
#[cfg(feature = "cloud")]
pub mod s3;
#[cfg(feature = "cloud")]
pub mod sftp;
pub mod virtual_vfs;
#[cfg(feature = "cloud")]
pub mod webdav;

#[cfg(all(test, feature = "cloud"))]
mod tests_cloud;

#[cfg(test)]
mod tests_local;

#[cfg(test)]
mod tests_archive;

#[cfg(test)]
mod tests_virtual;

pub use archive::{
    CompressedFileVfs, CompressionType, RarVfs, SevenZVfs, TarVfs, Writable7zVfs,
    WritableCompressedFileVfs, WritableTarVfs, WritableZipVfs, ZipVfs,
};
pub use local::LocalVfs;
#[cfg(feature = "cloud")]
pub use s3::{S3Auth, S3Config, S3Vfs};
#[cfg(feature = "cloud")]
pub use sftp::{SftpAuth, SftpConfig, SftpVfs};
pub use virtual_vfs::{FilteredVfs, UnionVfs};
#[cfg(feature = "cloud")]
pub use webdav::{WebDavAuth, WebDavConfig, WebDavVfs};
