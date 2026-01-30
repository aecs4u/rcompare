pub mod archive;
pub mod local;
pub mod s3;
pub mod sftp;
pub mod virtual_vfs;
pub mod webdav;

#[cfg(test)]
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
pub use s3::{S3Auth, S3Config, S3Vfs};
pub use sftp::{SftpAuth, SftpConfig, SftpVfs};
pub use virtual_vfs::{FilteredVfs, UnionVfs};
pub use webdav::{WebDavAuth, WebDavConfig, WebDavVfs};
