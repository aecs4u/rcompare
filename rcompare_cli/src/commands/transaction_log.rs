//! Durable JSONL journaling for mutating CLI commands.

use serde::Serialize;
use std::fs::{create_dir_all, File, OpenOptions};
use std::io::{self, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Serialize)]
struct TransactionEvent {
    schema_version: &'static str,
    timestamp: u64,
    operation: String,
    event: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    detail: Option<String>,
}

pub(crate) struct TransactionLog {
    operation: String,
    writer: BufWriter<File>,
}

impl TransactionLog {
    pub(crate) fn open(
        path: PathBuf,
        operation: &str,
        left: &Path,
        right: &Path,
    ) -> io::Result<Self> {
        if let Some(parent) = path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            create_dir_all(parent)?;
        }
        let file = OpenOptions::new().create(true).append(true).open(&path)?;
        let mut log = Self {
            operation: operation.to_string(),
            writer: BufWriter::new(file),
        };
        log.record(
            "run_started",
            None,
            None,
            Some(format!(
                "left={}; right={}",
                left.display(),
                right.display()
            )),
        )?;
        Ok(log)
    }

    pub(crate) fn action_planned(
        &mut self,
        code: &str,
        path: &str,
        detail: &str,
    ) -> io::Result<()> {
        self.record(
            "action_planned",
            Some(code),
            Some(path),
            Some(detail.to_string()),
        )
    }

    pub(crate) fn action_started(&mut self, code: &str, path: &str) -> io::Result<()> {
        self.record("action_started", Some(code), Some(path), None)
    }

    pub(crate) fn action_completed(&mut self, code: &str, path: &str) -> io::Result<()> {
        self.record("action_completed", Some(code), Some(path), None)
    }

    pub(crate) fn action_failed(&mut self, code: &str, path: &str, detail: &str) -> io::Result<()> {
        self.record(
            "action_failed",
            Some(code),
            Some(path),
            Some(detail.to_string()),
        )
    }

    pub(crate) fn finish(&mut self, successful: bool, detail: &str) -> io::Result<()> {
        self.record(
            if successful {
                "run_completed"
            } else {
                "run_failed"
            },
            None,
            None,
            Some(detail.to_string()),
        )
    }

    pub(crate) fn finish_cancelled(&mut self, detail: &str) -> io::Result<()> {
        self.record("run_cancelled", None, None, Some(detail.to_string()))
    }

    pub(crate) fn action_cancelled(&mut self, code: &str, path: &str) -> io::Result<()> {
        self.record("action_cancelled", Some(code), Some(path), None)
    }

    fn record(
        &mut self,
        event: &'static str,
        code: Option<&str>,
        path: Option<&str>,
        detail: Option<String>,
    ) -> io::Result<()> {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let event = TransactionEvent {
            schema_version: "1.0.0",
            timestamp,
            operation: self.operation.clone(),
            event,
            code: code.map(str::to_string),
            path: path.map(str::to_string),
            detail,
        };
        serde_json::to_writer(&mut self.writer, &event).map_err(|error| {
            io::Error::other(format!("failed to encode transaction event: {error}"))
        })?;
        self.writer.write_all(b"\n")?;
        self.writer.flush()?;
        self.writer.get_ref().sync_data()?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn appends_durable_jsonl_lifecycle_events() {
        let temp = TempDir::new().expect("temporary directory");
        let path = temp.path().join("transactions.jsonl");
        let mut log =
            TransactionLog::open(path.clone(), "copy", Path::new("left"), Path::new("right"))
                .expect("open log");
        log.action_planned("COPY", "file.txt", "copy file")
            .expect("planned event");
        log.action_started("COPY", "file.txt")
            .expect("started event");
        log.action_completed("COPY", "file.txt")
            .expect("completed event");
        log.finish(true, "1 action completed")
            .expect("finish event");

        let lines = std::fs::read_to_string(path)
            .expect("read log")
            .lines()
            .map(|line| serde_json::from_str::<serde_json::Value>(line).expect("valid JSON"))
            .collect::<Vec<_>>();
        assert_eq!(lines.len(), 5);
        assert_eq!(lines[0]["event"], "run_started");
        assert_eq!(lines[2]["event"], "action_started");
        assert_eq!(lines[4]["event"], "run_completed");
    }
}
