pub mod local;
pub mod archive;
pub mod sftp;
pub mod virtual_vfs;
pub mod s3;
pub mod webdav;

#[cfg(test)]
mod tests_cloud;

#[cfg(test)]
mod tests_local;

#[cfg(test)]
mod tests_archive;

#[cfg(test)]
mod tests_virtual;

pub use local::LocalVfs;
pub use archive::{
    ZipVfs, TarVfs, SevenZVfs, RarVfs,
    WritableZipVfs, WritableTarVfs, Writable7zVfs,
    CompressedFileVfs, WritableCompressedFileVfs, CompressionType,
};
pub use sftp::{SftpVfs, SftpConfig, SftpAuth};
pub use virtual_vfs::{FilteredVfs, UnionVfs};
pub use s3::{S3Vfs, S3Config, S3Auth};
pub use webdav::{WebDavVfs, WebDavConfig, WebDavAuth};
