use rcompare_common::{
    DifferenceType, FilePatch, Hunk, HunkType, PatchDifference, RCompareError,
};

/// Engine for applying/unapplying individual differences and blending
/// original file content into a parsed patch model.
pub struct PatchEngine;

impl PatchEngine {
    /// Apply a single difference (by flat index among non-Unchanged diffs).
    /// Adjusts tracking line numbers for all subsequent differences.
    pub fn apply_difference(patch: &mut FilePatch, flat_idx: usize) -> Result<(), RCompareError> {
        let indices = patch.difference_indices();
        if flat_idx >= indices.len() {
            return Err(RCompareError::PatchParse(format!(
                "Difference index {flat_idx} out of range (count: {})",
                indices.len()
            )));
        }
        let (hi, di) = indices[flat_idx];
        let diff = &patch.hunks[hi].differences[di];
        if diff.applied {
            return Ok(());
        }

        let delta = diff.dest_line_count() as isize - diff.source_line_count() as isize;
        let diff_dest_line = diff.dest_line_no;

        // Apply
        patch.hunks[hi].differences[di].applied = true;
        patch.hunks[hi].differences[di].unsaved =
            !patch.hunks[hi].differences[di].unsaved;
        patch.applied_count += 1;

        // Adjust tracking line numbers for all subsequent diffs
        Self::adjust_tracking(patch, diff_dest_line, delta);

        Ok(())
    }

    /// Unapply a single difference (by flat index among non-Unchanged diffs).
    pub fn unapply_difference(
        patch: &mut FilePatch,
        flat_idx: usize,
    ) -> Result<(), RCompareError> {
        let indices = patch.difference_indices();
        if flat_idx >= indices.len() {
            return Err(RCompareError::PatchParse(format!(
                "Difference index {flat_idx} out of range (count: {})",
                indices.len()
            )));
        }
        let (hi, di) = indices[flat_idx];
        let diff = &patch.hunks[hi].differences[di];
        if !diff.applied {
            return Ok(());
        }

        let delta = diff.dest_line_count() as isize - diff.source_line_count() as isize;
        let diff_dest_line = diff.dest_line_no;

        // Unapply
        patch.hunks[hi].differences[di].applied = false;
        patch.hunks[hi].differences[di].unsaved =
            !patch.hunks[hi].differences[di].unsaved;
        if patch.applied_count > 0 {
            patch.applied_count -= 1;
        }

        // Adjust tracking in reverse
        Self::adjust_tracking(patch, diff_dest_line, -delta);

        Ok(())
    }

    /// Apply all differences at once (no individual tracking updates).
    pub fn apply_all(patch: &mut FilePatch) -> Result<(), RCompareError> {
        let mut count = 0;
        for hunk in &mut patch.hunks {
            for diff in &mut hunk.differences {
                if diff.diff_type != DifferenceType::Unchanged && !diff.applied {
                    diff.applied = true;
                    diff.unsaved = !diff.unsaved;
                    count += 1;
                }
            }
        }
        patch.applied_count = count;
        Ok(())
    }

    /// Unapply all differences at once.
    pub fn unapply_all(patch: &mut FilePatch) -> Result<(), RCompareError> {
        for hunk in &mut patch.hunks {
            for diff in &mut hunk.differences {
                if diff.diff_type != DifferenceType::Unchanged && diff.applied {
                    diff.applied = false;
                    diff.unsaved = !diff.unsaved;
                }
            }
        }
        patch.applied_count = 0;
        Ok(())
    }

    /// Blend the original file content into the patch model.
    ///
    /// This inserts `AddedByBlend` hunks containing `Unchanged` context between
    /// and around the existing hunks, so the model represents the full file.
    /// Also detects conflicts where expected source lines don't match the actual file.
    pub fn blend_file(
        patch: &mut FilePatch,
        original_content: &str,
    ) -> Result<(), RCompareError> {
        let file_lines: Vec<&str> = split_lines(original_content);
        let mut src_line_no: usize = 1;
        let mut dst_line_no: usize = 1;
        let mut line_idx: usize = 0;
        let mut new_hunks: Vec<Hunk> = Vec::new();

        for hunk in &patch.hunks {
            // If there's a gap before this hunk, fill it with an AddedByBlend hunk
            if src_line_no < hunk.source_start {
                let mut blend_hunk = Hunk::new(src_line_no, dst_line_no);
                blend_hunk.hunk_type = HunkType::AddedByBlend;

                let mut diff = PatchDifference::new(
                    DifferenceType::Unchanged,
                    src_line_no,
                    dst_line_no,
                );

                while src_line_no < hunk.source_start && line_idx < file_lines.len() {
                    let line_content = file_lines[line_idx].to_string();
                    diff.source_lines.push(line_content.clone());
                    diff.dest_lines.push(line_content);
                    src_line_no += 1;
                    dst_line_no += 1;
                    line_idx += 1;
                }

                blend_hunk.differences.push(diff);
                blend_hunk.recompute_counts();
                new_hunks.push(blend_hunk);
            }

            // Skip over the lines covered by this hunk
            let size = hunk.source_count;
            let advance = size.min(file_lines.len().saturating_sub(line_idx));
            line_idx += advance;
            src_line_no += size;
            dst_line_no += hunk.dest_count;

            new_hunks.push(hunk.clone());
        }

        // If there are remaining lines after the last hunk
        if line_idx < file_lines.len() {
            let mut blend_hunk = Hunk::new(src_line_no, dst_line_no);
            blend_hunk.hunk_type = HunkType::AddedByBlend;

            let mut diff = PatchDifference::new(
                DifferenceType::Unchanged,
                src_line_no,
                dst_line_no,
            );

            while line_idx < file_lines.len() {
                let line_content = file_lines[line_idx].to_string();
                diff.source_lines.push(line_content.clone());
                diff.dest_lines.push(line_content);
                line_idx += 1;
            }

            blend_hunk.differences.push(diff);
            blend_hunk.recompute_counts();
            new_hunks.push(blend_hunk);
        }

        patch.hunks = new_hunks;
        patch.blended = true;

        Ok(())
    }

    /// Reconstruct the destination file content from the blended model.
    /// For each difference:
    /// - If applied: output source lines (original)
    /// - If not applied: output destination lines (patched)
    pub fn reconstruct_destination(patch: &FilePatch) -> Result<String, RCompareError> {
        let mut output = String::new();

        for hunk in &patch.hunks {
            for diff in &hunk.differences {
                if diff.applied {
                    // Applied means we show source (original) lines
                    for line in &diff.source_lines {
                        output.push_str(line);
                    }
                } else {
                    // Not applied means we show destination (patched) lines
                    for line in &diff.dest_lines {
                        output.push_str(line);
                    }
                }
            }
        }

        Ok(output)
    }

    /// Adjust tracking_dest_line_no for all diffs after the given dest_line_no.
    fn adjust_tracking(patch: &mut FilePatch, after_dest_line: usize, delta: isize) {
        for hunk in &mut patch.hunks {
            for diff in &mut hunk.differences {
                if diff.dest_line_no > after_dest_line {
                    if delta >= 0 {
                        diff.tracking_dest_line_no += delta as usize;
                    } else {
                        let abs_delta = (-delta) as usize;
                        diff.tracking_dest_line_no =
                            diff.tracking_dest_line_no.saturating_sub(abs_delta);
                    }
                }
            }
        }
    }
}

/// Split file content into lines, preserving line endings.
fn split_lines(content: &str) -> Vec<&str> {
    if content.is_empty() {
        return Vec::new();
    }
    let mut lines = Vec::new();
    let mut start = 0;
    for (i, ch) in content.char_indices() {
        if ch == '\n' {
            lines.push(&content[start..=i]);
            start = i + 1;
        }
    }
    // Trailing content without newline
    if start < content.len() {
        lines.push(&content[start..]);
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::patch_parser::PatchParser;

    fn make_simple_patch() -> FilePatch {
        let parser = PatchParser::new();
        let input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -1,5 +1,5 @@
 line1
-old2
+new2
 line3
-old4
+new4
 line5";
        let ps = parser.parse_string(input).unwrap();
        ps.files.into_iter().next().unwrap()
    }

    #[test]
    fn test_apply_difference() {
        let mut fp = make_simple_patch();
        assert_eq!(fp.applied_count, 0);

        PatchEngine::apply_difference(&mut fp, 0).unwrap();
        assert_eq!(fp.applied_count, 1);

        // Verify the first non-Unchanged diff is applied
        let indices = fp.difference_indices();
        let (hi, di) = indices[0];
        assert!(fp.hunks[hi].differences[di].applied);
    }

    #[test]
    fn test_unapply_difference() {
        let mut fp = make_simple_patch();
        PatchEngine::apply_difference(&mut fp, 0).unwrap();
        PatchEngine::unapply_difference(&mut fp, 0).unwrap();
        assert_eq!(fp.applied_count, 0);
    }

    #[test]
    fn test_apply_all() {
        let mut fp = make_simple_patch();
        PatchEngine::apply_all(&mut fp).unwrap();
        assert_eq!(fp.applied_count, fp.difference_count());
    }

    #[test]
    fn test_unapply_all() {
        let mut fp = make_simple_patch();
        PatchEngine::apply_all(&mut fp).unwrap();
        PatchEngine::unapply_all(&mut fp).unwrap();
        assert_eq!(fp.applied_count, 0);
    }

    #[test]
    fn test_blend_file() {
        let parser = PatchParser::new();
        let diff_input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -3,3 +3,3 @@
 line3
-old4
+new4
 line5";
        let mut ps = parser.parse_string(diff_input).unwrap();
        let fp = &mut ps.files[0];

        let original = "line1\nline2\nline3\nold4\nline5\nline6\n";
        PatchEngine::blend_file(fp, original).unwrap();

        assert!(fp.blended);
        // Should have: AddedByBlend(lines 1-2), Original hunk(lines 3-5), AddedByBlend(line 6)
        assert!(fp.hunks.len() >= 2);
        assert_eq!(fp.hunks[0].hunk_type, HunkType::AddedByBlend);
    }

    #[test]
    fn test_reconstruct_destination() {
        let parser = PatchParser::new();
        let diff_input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -1,3 +1,3 @@
 line1
-old
+new
 line3";
        let mut ps = parser.parse_string(diff_input).unwrap();
        let fp = &mut ps.files[0];

        let original = "line1\nold\nline3\n";
        PatchEngine::blend_file(fp, original).unwrap();

        // Without applying, destination shows patched version
        let result = PatchEngine::reconstruct_destination(fp).unwrap();
        assert!(result.contains("new"));
        assert!(!result.contains("old"));
    }

    #[test]
    fn test_split_lines() {
        let lines = split_lines("a\nb\nc\n");
        assert_eq!(lines, vec!["a\n", "b\n", "c\n"]);

        let lines = split_lines("a\nb");
        assert_eq!(lines, vec!["a\n", "b"]);

        let lines = split_lines("");
        assert!(lines.is_empty());
    }

    #[test]
    fn test_out_of_range() {
        let mut fp = make_simple_patch();
        let result = PatchEngine::apply_difference(&mut fp, 999);
        assert!(result.is_err());
    }
}
