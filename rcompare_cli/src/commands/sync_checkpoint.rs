//! Durable metadata for interrupted sync runs.

use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tempfile::NamedTempFile;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct SyncCheckpoint {
    pub(crate) id: String,
    pub(crate) schema_version: String,
    pub(crate) created_at: u128,
    pub(crate) updated_at: u128,
    pub(crate) status: String,
    pub(crate) left: String,
    pub(crate) right: String,
    pub(crate) direction: String,
    pub(crate) delete_mode: String,
    pub(crate) conflict_policy: String,
    pub(crate) ignore_patterns: Vec<String>,
    pub(crate) follow_symlinks: bool,
    pub(crate) verify_hashes: bool,
    pub(crate) no_verify_hashes: bool,
    pub(crate) strict: bool,
    pub(crate) total_actions: usize,
    pub(crate) completed_actions: usize,
    pub(crate) remaining_actions: usize,
    pub(crate) failed_actions: usize,
}

impl SyncCheckpoint {
    pub(crate) fn new(
        left: &Path,
        right: &Path,
        direction: &str,
        delete_mode: &str,
        conflict_policy: &str,
        ignore_patterns: &[String],
        follow_symlinks: bool,
        verify_hashes: bool,
        no_verify_hashes: bool,
        strict: bool,
    ) -> Self {
        let created_at = now_millis();
        let id = format!("sync-{created_at}-{}", std::process::id());
        Self {
            id,
            schema_version: "1.0.0".to_string(),
            created_at,
            updated_at: created_at,
            status: "running".to_string(),
            left: left.to_string_lossy().into_owned(),
            right: right.to_string_lossy().into_owned(),
            direction: direction.to_string(),
            delete_mode: delete_mode.to_string(),
            conflict_policy: conflict_policy.to_string(),
            ignore_patterns: ignore_patterns.to_vec(),
            follow_symlinks,
            verify_hashes,
            no_verify_hashes,
            strict,
            total_actions: 0,
            completed_actions: 0,
            remaining_actions: 0,
            failed_actions: 0,
        }
    }

    pub(crate) fn validate_resume(
        &self,
        left: &Path,
        right: &Path,
        direction: &str,
        delete_mode: &str,
        conflict_policy: &str,
        ignore_patterns: &[String],
        follow_symlinks: bool,
        verify_hashes: bool,
        no_verify_hashes: bool,
        strict: bool,
    ) -> Result<(), String> {
        if self.left != left.to_string_lossy()
            || self.right != right.to_string_lossy()
            || self.direction != direction
            || self.delete_mode != delete_mode
            || self.conflict_policy != conflict_policy
            || self.ignore_patterns != ignore_patterns
            || self.follow_symlinks != follow_symlinks
            || self.verify_hashes != verify_hashes
            || self.no_verify_hashes != no_verify_hashes
            || self.strict != strict
        {
            return Err("resume options do not match the saved sync".to_string());
        }
        if self.status == "completed" {
            return Err("sync checkpoint is already completed".to_string());
        }
        Ok(())
    }

    pub(crate) fn save(&mut self, dir: &Path) -> io::Result<()> {
        fs::create_dir_all(dir)?;
        self.updated_at = now_millis();
        let destination = manifest_path(dir, &self.id);
        let data = serde_json::to_vec_pretty(self)
            .map_err(|error| io::Error::other(format!("encode sync checkpoint: {error}")))?;
        let mut file = NamedTempFile::new_in(dir)?;
        file.write_all(&data)?;
        file.as_file().sync_all()?;
        file.persist(&destination)?;
        if let Ok(dir_file) = File::open(dir) {
            let _ = dir_file.sync_all();
        }
        Ok(())
    }

    pub(crate) fn load(dir: &Path, id: &str) -> io::Result<Self> {
        if !valid_id(id) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid sync checkpoint id",
            ));
        }
        let data = fs::read(manifest_path(dir, id))?;
        serde_json::from_slice(&data)
            .map_err(|error| io::Error::other(format!("parse sync checkpoint: {error}")))
    }

    pub(crate) fn list(dir: &Path) -> io::Result<Vec<Self>> {
        if !dir.exists() {
            return Ok(Vec::new());
        }
        let mut checkpoints = Vec::new();
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().is_some_and(|ext| ext == "json")
                && path
                    .file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| name.starts_with("sync-") && name.ends_with(".json"))
            {
                let data = fs::read(&path)?;
                let checkpoint: Self = serde_json::from_slice(&data).map_err(|error| {
                    io::Error::other(format!("parse {}: {error}", path.display()))
                })?;
                checkpoints.push(checkpoint);
            }
        }
        checkpoints.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
        Ok(checkpoints)
    }

    pub(crate) fn discard(dir: &Path, id: &str) -> io::Result<()> {
        let checkpoint = Self::load(dir, id)?;
        cleanup_file_checkpoints(dir, &checkpoint);
        fs::remove_file(manifest_path(dir, id))
    }
}

fn cleanup_file_checkpoints(dir: &Path, sync: &SyncCheckpoint) {
    let left = Path::new(&sync.left);
    let right = Path::new(&sync.right);
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().is_none_or(|ext| ext != "json")
            || !path
                .file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("checkpoint_"))
        {
            continue;
        }
        let Ok(data) = fs::read(&path) else {
            continue;
        };
        let Ok(value) = serde_json::from_slice::<serde_json::Value>(&data) else {
            continue;
        };
        let Some(source) = value.get("source").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let Some(destination) = value.get("destination").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let source = Path::new(source);
        let destination = Path::new(destination);
        let belongs_to_sync = (source.starts_with(left) && destination.starts_with(right))
            || (source.starts_with(right) && destination.starts_with(left));
        if belongs_to_sync {
            let _ = fs::remove_file(path);
        }
    }
}

fn manifest_path(dir: &Path, id: &str) -> PathBuf {
    dir.join(format!("{id}.json"))
}

fn valid_id(id: &str) -> bool {
    id.starts_with("sync-")
        && id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn checkpoint_round_trips_and_rejects_changed_roots_or_options() {
        let temp = tempfile::tempdir().expect("temporary directory");
        let left = Path::new("/tmp/left");
        let right = Path::new("/tmp/right");
        let ignores = vec!["*.tmp".to_string()];
        let mut checkpoint = SyncCheckpoint::new(
            left,
            right,
            "left_to_right",
            "trash",
            "newest",
            &ignores,
            false,
            false,
            false,
            false,
        );
        checkpoint.save(temp.path()).expect("save checkpoint");
        let mut loaded =
            SyncCheckpoint::load(temp.path(), &checkpoint.id).expect("load checkpoint");
        loaded
            .validate_resume(
                left,
                right,
                "left_to_right",
                "trash",
                "newest",
                &ignores,
                false,
                false,
                false,
                false,
            )
            .expect("matching options resume");
        assert!(loaded
            .validate_resume(
                left,
                right,
                "right_to_left",
                "trash",
                "newest",
                &ignores,
                false,
                false,
                false,
                false,
            )
            .is_err());
        loaded.status = "cancelled".to_string();
        loaded
            .save(temp.path())
            .expect("replace checkpoint atomically");
        assert_eq!(
            SyncCheckpoint::load(temp.path(), &checkpoint.id)
                .unwrap()
                .status,
            "cancelled"
        );
        assert_eq!(SyncCheckpoint::list(temp.path()).unwrap().len(), 1);
    }

    #[test]
    fn discard_removes_only_matching_file_checkpoint_metadata() {
        let temp = tempfile::tempdir().expect("temporary directory");
        let left = temp.path().join("left");
        let right = temp.path().join("right");
        fs::create_dir_all(&left).expect("left directory");
        fs::create_dir_all(&right).expect("right directory");
        let mut checkpoint = SyncCheckpoint::new(
            &left,
            &right,
            "left_to_right",
            "trash",
            "newest",
            &[],
            false,
            false,
            false,
            false,
        );
        checkpoint.save(temp.path()).expect("save checkpoint");
        let file_checkpoint = temp.path().join("checkpoint_test.json");
        fs::write(
            &file_checkpoint,
            serde_json::json!({
                "source": left.join("large.bin"),
                "destination": right.join("large.bin")
            })
            .to_string(),
        )
        .expect("write file checkpoint");
        SyncCheckpoint::discard(temp.path(), &checkpoint.id).expect("discard sync");
        assert!(!file_checkpoint.exists());
        assert!(SyncCheckpoint::list(temp.path()).unwrap().is_empty());
    }
}
