//! Structured progress reporting for long-running operations.
//!
//! Follows the Czkawka pattern: a dedicated progress thread reads atomic counters
//! and sends [`ProgressData`] snapshots through a crossbeam channel at a fixed
//! interval. Consumers (CLI, GUI) receive typed updates without polling.

use crossbeam::channel::{Receiver, Sender};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

/// How often the progress thread sends updates (milliseconds).
const PROGRESS_INTERVAL_MS: u64 = 200;

/// Current stage of a scan/compare operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScanStage {
    /// Collecting file entries from the left source.
    ScanningLeft,
    /// Collecting file entries from the right source.
    ScanningRight,
    /// Comparing file metadata (sizes, timestamps).
    Comparing,
    /// Computing content hashes for verification.
    Hashing,
    /// Running specialized diff (text, image, CSV, …).
    DiffingFiles,
    /// Persisting hash cache to disk.
    SavingCache,
    /// Operation complete.
    Done,
}

impl std::fmt::Display for ScanStage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::ScanningLeft => write!(f, "Scanning left"),
            Self::ScanningRight => write!(f, "Scanning right"),
            Self::Comparing => write!(f, "Comparing"),
            Self::Hashing => write!(f, "Hashing"),
            Self::DiffingFiles => write!(f, "Diffing files"),
            Self::SavingCache => write!(f, "Saving cache"),
            Self::Done => write!(f, "Done"),
        }
    }
}

/// A snapshot of progress data sent from the progress thread.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProgressData {
    /// Current operation stage.
    pub stage: ScanStage,
    /// Index of the current stage (0-based).
    pub stage_index: u8,
    /// Total number of stages.
    pub stage_count: u8,
    /// Number of entries processed so far in this stage.
    pub entries_done: usize,
    /// Total entries expected in this stage (0 if unknown).
    pub entries_total: usize,
    /// Bytes processed so far in this stage.
    pub bytes_done: u64,
    /// Total bytes expected in this stage (0 if unknown).
    pub bytes_total: u64,
}

impl ProgressData {
    /// Convenience: percentage complete (0–100). Returns 0 when total is unknown.
    pub fn percent(&self) -> u8 {
        if self.entries_total > 0 {
            ((self.entries_done as f64 / self.entries_total as f64) * 100.0).min(100.0) as u8
        } else {
            0
        }
    }
}

/// Shared atomic counters that workers increment; the progress thread reads them.
#[derive(Debug)]
pub struct ProgressCounters {
    pub entries_done: AtomicUsize,
    pub entries_total: AtomicUsize,
    pub bytes_done: AtomicU64,
    pub bytes_total: AtomicU64,
}

impl Default for ProgressCounters {
    fn default() -> Self {
        Self {
            entries_done: AtomicUsize::new(0),
            entries_total: AtomicUsize::new(0),
            bytes_done: AtomicU64::new(0),
            bytes_total: AtomicU64::new(0),
        }
    }
}

impl ProgressCounters {
    /// Reset all counters to zero.
    pub fn reset(&self) {
        self.entries_done.store(0, Ordering::Relaxed);
        self.entries_total.store(0, Ordering::Relaxed);
        self.bytes_done.store(0, Ordering::Relaxed);
        self.bytes_total.store(0, Ordering::Relaxed);
    }
}

/// Manages a background thread that periodically samples [`ProgressCounters`]
/// and sends [`ProgressData`] through a crossbeam channel.
pub struct ProgressHandler {
    /// Channel receiver — the consumer side (CLI / GUI).
    pub receiver: Receiver<ProgressData>,
    /// Shared counters that scan/compare code increments.
    pub counters: Arc<ProgressCounters>,
    /// Set to `true` to stop the background thread.
    stop_flag: Arc<AtomicBool>,
    /// Join handle for the progress thread.
    _handle: Option<thread::JoinHandle<()>>,
}

impl ProgressHandler {
    /// Spawn a new progress-reporting thread.
    ///
    /// The returned [`ProgressHandler`] owns both the receiver and the shared
    /// counters. Workers should clone `handler.counters` and increment them.
    pub fn new() -> Self {
        let (tx, rx): (Sender<ProgressData>, Receiver<ProgressData>) =
            crossbeam::channel::bounded(64);
        let counters = Arc::new(ProgressCounters::default());
        let stop_flag = Arc::new(AtomicBool::new(false));

        let counters_clone = Arc::clone(&counters);
        let stop_clone = Arc::clone(&stop_flag);

        let handle = thread::Builder::new()
            .name("rcompare-progress".into())
            .spawn(move || {
                // Start at ScanningLeft; the caller updates via set_stage().
                let mut current_stage = ScanStage::ScanningLeft;
                let mut stage_index: u8 = 0;

                while !stop_clone.load(Ordering::Relaxed) {
                    let data = ProgressData {
                        stage: current_stage,
                        stage_index,
                        stage_count: 6, // total stages in a full scan
                        entries_done: counters_clone.entries_done.load(Ordering::Relaxed),
                        entries_total: counters_clone.entries_total.load(Ordering::Relaxed),
                        bytes_done: counters_clone.bytes_done.load(Ordering::Relaxed),
                        bytes_total: counters_clone.bytes_total.load(Ordering::Relaxed),
                    };
                    // Ignore send errors (receiver dropped).
                    let _ = tx.send(data);
                    thread::sleep(Duration::from_millis(PROGRESS_INTERVAL_MS));
                }

                // Send a final "Done" message.
                let _ = tx.send(ProgressData {
                    stage: ScanStage::Done,
                    stage_index: 5,
                    stage_count: 6,
                    entries_done: counters_clone.entries_done.load(Ordering::Relaxed),
                    entries_total: counters_clone.entries_total.load(Ordering::Relaxed),
                    bytes_done: counters_clone.bytes_done.load(Ordering::Relaxed),
                    bytes_total: counters_clone.bytes_total.load(Ordering::Relaxed),
                });
            })
            .expect("failed to spawn progress thread");

        Self {
            receiver: rx,
            counters,
            stop_flag,
            _handle: Some(handle),
        }
    }

    /// Signal the progress thread to stop.
    pub fn stop(&self) {
        self.stop_flag.store(true, Ordering::Relaxed);
    }
}

impl Drop for ProgressHandler {
    fn drop(&mut self) {
        self.stop();
        if let Some(handle) = self._handle.take() {
            let _ = handle.join();
        }
    }
}

/// Create a simple progress sender/receiver pair for use with
/// [`ComparisonEngine::compare_with_vfs_and_progress`].
///
/// Returns `(sender, receiver)`. The sender is a closure `Fn(usize, usize)` suitable
/// for the existing progress callback signature.
pub fn simple_progress_channel() -> (Sender<ProgressData>, Receiver<ProgressData>) {
    crossbeam::channel::bounded(64)
}
