use rcompare_common::{
    DifferenceType, FilePatch, Hunk, HunkType, PatchDifference, PatchSet,
};

/// Serializer that recreates unified diff text from a PatchSet model.
///
/// This is the inverse of parsing: given a PatchSet, produce the unified diff
/// text that would parse back to the same model. `AddedByBlend` hunks are
/// skipped since they represent original file context, not diff content.
pub struct PatchSerializer;

impl PatchSerializer {
    /// Serialize an entire PatchSet to unified diff text.
    pub fn serialize(patch_set: &PatchSet) -> String {
        let mut output = String::new();
        for fp in &patch_set.files {
            output.push_str(&Self::serialize_file_patch(fp));
        }
        output
    }

    /// Serialize a single FilePatch to unified diff text.
    pub fn serialize_file_patch(fp: &FilePatch) -> String {
        let mut output = String::new();

        // File headers
        output.push_str(&format!("--- {}", escape_path(&fp.source)));
        if !fp.source_timestamp.is_empty() {
            output.push('\t');
            output.push_str(&fp.source_timestamp);
        }
        if !fp.source_revision.is_empty() {
            output.push('\t');
            output.push_str(&fp.source_revision);
        }
        output.push('\n');

        output.push_str(&format!("+++ {}", escape_path(&fp.destination)));
        if !fp.dest_timestamp.is_empty() {
            output.push('\t');
            output.push_str(&fp.dest_timestamp);
        }
        if !fp.dest_revision.is_empty() {
            output.push('\t');
            output.push_str(&fp.dest_revision);
        }
        output.push('\n');

        // Hunks (skip AddedByBlend)
        for hunk in &fp.hunks {
            if hunk.hunk_type == HunkType::AddedByBlend {
                continue;
            }
            output.push_str(&Self::serialize_hunk(hunk));
        }

        output
    }

    fn serialize_hunk(hunk: &Hunk) -> String {
        let mut body = String::new();
        let mut src_count = 0usize;
        let mut dst_count = 0usize;

        for diff in &hunk.differences {
            let diff_text = Self::serialize_difference(diff);
            body.push_str(&diff_text);

            match diff.diff_type {
                DifferenceType::Unchanged => {
                    src_count += diff.source_line_count();
                    dst_count += diff.dest_line_count();
                }
                DifferenceType::Change => {
                    src_count += diff.source_line_count();
                    dst_count += diff.dest_line_count();
                }
                DifferenceType::Delete => {
                    src_count += diff.source_line_count();
                }
                DifferenceType::Insert => {
                    dst_count += diff.dest_line_count();
                }
            }
        }

        let mut header = format!(
            "@@ -{},{} +{},{} @@",
            hunk.source_start, src_count, hunk.dest_start, dst_count
        );
        if let Some(ref func) = hunk.function_name {
            header.push(' ');
            header.push_str(func);
        }
        header.push('\n');

        format!("{header}{body}")
    }

    fn serialize_difference(diff: &PatchDifference) -> String {
        let mut output = String::new();

        match diff.diff_type {
            DifferenceType::Unchanged => {
                for line in &diff.source_lines {
                    output.push(' ');
                    output.push_str(&strip_trailing_newline(line));
                    output.push('\n');
                }
            }
            DifferenceType::Change => {
                for line in &diff.source_lines {
                    output.push('-');
                    output.push_str(&strip_trailing_newline(line));
                    output.push('\n');
                }
                for line in &diff.dest_lines {
                    output.push('+');
                    output.push_str(&strip_trailing_newline(line));
                    output.push('\n');
                }
            }
            DifferenceType::Delete => {
                for line in &diff.source_lines {
                    output.push('-');
                    output.push_str(&strip_trailing_newline(line));
                    output.push('\n');
                }
            }
            DifferenceType::Insert => {
                for line in &diff.dest_lines {
                    output.push('+');
                    output.push_str(&strip_trailing_newline(line));
                    output.push('\n');
                }
            }
        }

        output
    }
}

fn escape_path(path: &str) -> String {
    if path.contains(' ') {
        format!("\"{}\"", path.replace('\\', "\\\\").replace('"', "\\\""))
    } else {
        path.to_string()
    }
}

fn strip_trailing_newline(s: &str) -> &str {
    s.strip_suffix('\n').unwrap_or(s)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::patch_parser::PatchParser;

    #[test]
    fn test_round_trip_unified() {
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
 line5
";
        let parser = PatchParser::new();
        let ps = parser.parse_string(input).unwrap();
        let serialized = PatchSerializer::serialize(&ps);

        // Re-parse the serialized output
        let ps2 = parser.parse_string(&serialized).unwrap();
        assert_eq!(ps.files.len(), ps2.files.len());
        assert_eq!(
            ps.files[0].hunks[0].differences.len(),
            ps2.files[0].hunks[0].differences.len()
        );
    }

    #[test]
    fn test_serialize_insert() {
        let input = "\
--- a/file.txt
+++ b/file.txt
@@ -1,2 +1,4 @@
 line1
+added1
+added2
 line2
";
        let parser = PatchParser::new();
        let ps = parser.parse_string(input).unwrap();
        let serialized = PatchSerializer::serialize(&ps);

        assert!(serialized.contains("+added1"));
        assert!(serialized.contains("+added2"));
        assert!(serialized.contains(" line1"));
    }

    #[test]
    fn test_serialize_skips_blended_hunks() {
        let input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -3,3 +3,3 @@
 line3
-old4
+new4
 line5
";
        let parser = PatchParser::new();
        let mut ps = parser.parse_string(input).unwrap();

        // Blend original file
        let original = "line1\nline2\nline3\nold4\nline5\nline6\n";
        crate::patch_engine::PatchEngine::blend_file(&mut ps.files[0], original).unwrap();

        // Serialize — should NOT contain the blended context lines
        let serialized = PatchSerializer::serialize(&ps);
        // The blended context (line1, line2, line6) should NOT appear as diff lines
        assert!(!serialized.contains(" line1"));
        assert!(!serialized.contains(" line6"));
        // But the original hunk content should be there
        assert!(serialized.contains("-old4"));
        assert!(serialized.contains("+new4"));
    }

    #[test]
    fn test_serialize_with_function_name() {
        let input = "\
--- a/file.c
+++ b/file.c
@@ -10,3 +10,3 @@ int main()
 line10
-old
+new
 line12
";
        let parser = PatchParser::new();
        let ps = parser.parse_string(input).unwrap();
        let serialized = PatchSerializer::serialize(&ps);
        assert!(serialized.contains("@@ -10,3 +10,3 @@ int main()"));
    }

    #[test]
    fn test_serialize_empty_patchset() {
        let ps = PatchSet::new();
        let serialized = PatchSerializer::serialize(&ps);
        assert!(serialized.is_empty());
    }
}
