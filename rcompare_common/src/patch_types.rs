use serde::{Deserialize, Serialize};

/// Diff output format
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum DiffFormat {
    Unknown = 0,
    Unified = 1,
    Context = 2,
    Normal = 3,
    Ed = 4,
    Rcs = 5,
}

/// Which tool generated the diff output
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum DiffGenerator {
    Unknown = 0,
    Diff = 1,
    CvsDiff = 2,
    Perforce = 3,
    SubVersion = 4,
}

/// Type of a single difference block
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum DifferenceType {
    Unchanged = 0,
    Change = 1,
    Insert = 2,
    Delete = 3,
}

/// Whether a hunk was part of the original diff or added during blending
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HunkType {
    /// Original hunk from the parsed diff
    Normal,
    /// Context hunk added by blending original file into the model
    AddedByBlend,
}

/// A complete patch set parsed from diff output, potentially covering multiple files
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatchSet {
    /// One FilePatch per file pair in the diff
    pub files: Vec<FilePatch>,
    /// Detected diff format
    pub format: DiffFormat,
    /// Detected generator tool
    pub generator: DiffGenerator,
}

impl PatchSet {
    pub fn new() -> Self {
        Self {
            files: Vec::new(),
            format: DiffFormat::Unknown,
            generator: DiffGenerator::Unknown,
        }
    }
}

impl Default for PatchSet {
    fn default() -> Self {
        Self::new()
    }
}

/// Diff for a single file pair (source → destination)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FilePatch {
    /// Full source path from the diff header
    pub source: String,
    /// Full destination path from the diff header
    pub destination: String,
    /// Source file timestamp from the diff header
    pub source_timestamp: String,
    /// Destination file timestamp from the diff header
    pub dest_timestamp: String,
    /// Source revision string (e.g., from CVS or Perforce)
    pub source_revision: String,
    /// Destination revision string
    pub dest_revision: String,
    /// Ordered list of hunks (includes both original and blended hunks)
    pub hunks: Vec<Hunk>,
    /// Number of currently applied differences
    pub applied_count: usize,
    /// Whether the original file has been blended into this model
    pub blended: bool,
}

impl FilePatch {
    pub fn new() -> Self {
        Self {
            source: String::new(),
            destination: String::new(),
            source_timestamp: String::new(),
            dest_timestamp: String::new(),
            source_revision: String::new(),
            dest_revision: String::new(),
            hunks: Vec::new(),
            applied_count: 0,
            blended: false,
        }
    }

    /// Total number of differences (non-Unchanged) across all hunks
    pub fn difference_count(&self) -> usize {
        self.hunks
            .iter()
            .flat_map(|h| &h.differences)
            .filter(|d| d.diff_type != DifferenceType::Unchanged)
            .count()
    }

    /// Collect all differences (non-Unchanged) as flat indices: (hunk_idx, diff_idx)
    pub fn difference_indices(&self) -> Vec<(usize, usize)> {
        let mut indices = Vec::new();
        for (hi, hunk) in self.hunks.iter().enumerate() {
            for (di, diff) in hunk.differences.iter().enumerate() {
                if diff.diff_type != DifferenceType::Unchanged {
                    indices.push((hi, di));
                }
            }
        }
        indices
    }

    /// Check if there are any unsaved changes
    pub fn has_unsaved_changes(&self) -> bool {
        self.hunks
            .iter()
            .flat_map(|h| &h.differences)
            .any(|d| d.unsaved)
    }
}

impl Default for FilePatch {
    fn default() -> Self {
        Self::new()
    }
}

/// A hunk groups related differences with surrounding context
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hunk {
    /// Starting line number in the source file (1-based)
    pub source_start: usize,
    /// Number of lines from the source file in this hunk
    pub source_count: usize,
    /// Starting line number in the destination file (1-based)
    pub dest_start: usize,
    /// Number of lines from the destination file in this hunk
    pub dest_count: usize,
    /// Optional function/context name from the hunk header
    pub function_name: Option<String>,
    /// Whether this hunk was in the original diff or added by blending
    pub hunk_type: HunkType,
    /// Ordered differences within this hunk (including Unchanged context)
    pub differences: Vec<PatchDifference>,
}

impl Hunk {
    pub fn new(source_start: usize, dest_start: usize) -> Self {
        Self {
            source_start,
            source_count: 0,
            dest_start,
            dest_count: 0,
            function_name: None,
            hunk_type: HunkType::Normal,
            differences: Vec::new(),
        }
    }

    /// Recompute source_count and dest_count from the differences
    pub fn recompute_counts(&mut self) {
        let mut src = 0usize;
        let mut dst = 0usize;
        for diff in &self.differences {
            match diff.diff_type {
                DifferenceType::Unchanged | DifferenceType::Change => {
                    src += diff.source_lines.len();
                    dst += diff.dest_lines.len();
                }
                DifferenceType::Delete => {
                    src += diff.source_lines.len();
                }
                DifferenceType::Insert => {
                    dst += diff.dest_lines.len();
                }
            }
        }
        self.source_count = src;
        self.dest_count = dst;
    }
}

/// A single difference block (change, insert, delete, or unchanged context)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatchDifference {
    /// The type of change
    pub diff_type: DifferenceType,
    /// Starting line number in the source file (1-based)
    pub source_line_no: usize,
    /// Starting line number in the destination file (1-based)
    pub dest_line_no: usize,
    /// Adjusted destination line number accounting for previously applied patches
    pub tracking_dest_line_no: usize,
    /// Lines from the source file
    pub source_lines: Vec<String>,
    /// Lines from the destination file
    pub dest_lines: Vec<String>,
    /// Whether this difference has been applied (toggled by patch engine)
    pub applied: bool,
    /// Whether source lines conflict with the actual file content (set during blending)
    pub conflict: bool,
    /// Whether this difference has been modified since last save
    pub unsaved: bool,
}

impl PatchDifference {
    pub fn new(
        diff_type: DifferenceType,
        source_line_no: usize,
        dest_line_no: usize,
    ) -> Self {
        Self {
            diff_type,
            source_line_no,
            dest_line_no,
            tracking_dest_line_no: dest_line_no,
            source_lines: Vec::new(),
            dest_lines: Vec::new(),
            applied: false,
            conflict: false,
            unsaved: false,
        }
    }

    /// Number of source lines
    pub fn source_line_count(&self) -> usize {
        self.source_lines.len()
    }

    /// Number of destination lines
    pub fn dest_line_count(&self) -> usize {
        self.dest_lines.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_patch_set_default() {
        let ps = PatchSet::new();
        assert!(ps.files.is_empty());
        assert_eq!(ps.format, DiffFormat::Unknown);
        assert_eq!(ps.generator, DiffGenerator::Unknown);
    }

    #[test]
    fn test_file_patch_difference_count() {
        let mut fp = FilePatch::new();
        let mut hunk = Hunk::new(1, 1);
        hunk.differences.push(PatchDifference::new(DifferenceType::Unchanged, 1, 1));
        hunk.differences.push(PatchDifference::new(DifferenceType::Change, 2, 2));
        hunk.differences.push(PatchDifference::new(DifferenceType::Insert, 0, 3));
        hunk.differences.push(PatchDifference::new(DifferenceType::Unchanged, 3, 4));
        fp.hunks.push(hunk);
        assert_eq!(fp.difference_count(), 2); // Change + Insert, not Unchanged
    }

    #[test]
    fn test_hunk_recompute_counts() {
        let mut hunk = Hunk::new(1, 1);
        let mut d1 = PatchDifference::new(DifferenceType::Unchanged, 1, 1);
        d1.source_lines.push("ctx\n".to_string());
        d1.dest_lines.push("ctx\n".to_string());

        let mut d2 = PatchDifference::new(DifferenceType::Change, 2, 2);
        d2.source_lines.push("old\n".to_string());
        d2.dest_lines.push("new1\n".to_string());
        d2.dest_lines.push("new2\n".to_string());

        hunk.differences.push(d1);
        hunk.differences.push(d2);
        hunk.recompute_counts();
        assert_eq!(hunk.source_count, 2);
        assert_eq!(hunk.dest_count, 3);
    }

    #[test]
    fn test_difference_line_counts() {
        let mut d = PatchDifference::new(DifferenceType::Delete, 5, 5);
        d.source_lines.push("line1\n".to_string());
        d.source_lines.push("line2\n".to_string());
        assert_eq!(d.source_line_count(), 2);
        assert_eq!(d.dest_line_count(), 0);
    }
}
