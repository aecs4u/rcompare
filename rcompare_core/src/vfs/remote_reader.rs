use std::fs::{File, OpenOptions};
use std::io::{self, Read};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_SPOOL_ID: AtomicU64 = AtomicU64::new(0);

/// Create a unique temporary file used to spool a remote response without
/// keeping the whole object in memory.
pub(crate) fn create_spool_file() -> io::Result<(PathBuf, File)> {
    let temp_dir = std::env::temp_dir();
    loop {
        let id = NEXT_SPOOL_ID.fetch_add(1, Ordering::Relaxed);
        let path = temp_dir.join(format!("rcompare-remote-{}-{id}.tmp", std::process::id()));
        match OpenOptions::new().create_new(true).write(true).open(&path) {
            Ok(file) => return Ok((path, file)),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
    }
}

pub(crate) fn open_spool_reader(path: PathBuf) -> io::Result<Box<dyn Read + Send>> {
    let file = match File::open(&path) {
        Ok(file) => file,
        Err(error) => {
            let _ = std::fs::remove_file(&path);
            return Err(error);
        }
    };
    Ok(Box::new(SpoolReader { file, path }))
}

struct SpoolReader {
    file: File,
    path: PathBuf,
}

impl Read for SpoolReader {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        self.file.read(buffer)
    }
}

impl Drop for SpoolReader {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};

    #[test]
    fn spool_reader_cleans_up_after_reading() {
        let (path, mut file) = create_spool_file().expect("create spool");
        file.write_all(b"remote content").expect("write spool");
        file.sync_all().expect("sync spool");
        drop(file);

        let mut reader = open_spool_reader(path.clone()).expect("open spool");
        let mut content = String::new();
        reader.read_to_string(&mut content).expect("read spool");
        assert_eq!(content, "remote content");
        drop(reader);
        assert!(!path.exists());
    }
}
