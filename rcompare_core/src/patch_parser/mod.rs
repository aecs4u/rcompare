pub mod context;
pub mod ed;
pub mod normal;
pub mod rcs;
pub mod unified;

use rcompare_common::{
    DiffFormat, DiffGenerator, PatchSet, RCompareError,
};
use regex::Regex;
use std::path::Path;
use std::sync::LazyLock;

// Patterns for format detection
static PAT_UNIFIED: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^@@\s").unwrap());
static PAT_CONTEXT: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\*{15}").unwrap());
static PAT_NORMAL: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\d+(?:,\d+)?[acd]\d+(?:,\d+)?$").unwrap());
static PAT_RCS: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[ad]\d+\s+\d+$").unwrap());
static PAT_ED: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\d+(?:,\d+)?[acd]$").unwrap());

/// Parser for diff/patch output in multiple formats.
///
/// Automatically detects the generator (CVS, Perforce, plain diff) and
/// the format (unified, context, normal, ed, RCS), then delegates to
/// the appropriate sub-parser.
pub struct PatchParser;

impl PatchParser {
    pub fn new() -> Self {
        Self
    }

    /// Parse diff text from a string.
    pub fn parse_string(&self, input: &str) -> Result<PatchSet, RCompareError> {
        let mut lines_owned: Vec<String> = input.lines().map(|l| l.to_string()).collect();

        // Clean up "\ No newline at end of file" markers
        Self::clean_no_newline(&mut lines_owned);

        let lines: Vec<&str> = lines_owned.iter().map(|s| s.as_str()).collect();

        let generator = Self::detect_generator(&lines);
        let format = Self::detect_format(&lines);

        let file_patches = match format {
            DiffFormat::Unified => unified::parse_unified(&lines)?,
            DiffFormat::Context => context::parse_context(&lines)?,
            DiffFormat::Normal => normal::parse_normal(&lines)?,
            DiffFormat::Ed => ed::parse_ed(&lines)?,
            DiffFormat::Rcs => rcs::parse_rcs(&lines)?,
            DiffFormat::Unknown => {
                // Try unified first (most common), fall back to normal
                let result = unified::parse_unified(&lines)?;
                if !result.is_empty() {
                    result
                } else {
                    normal::parse_normal(&lines)?
                }
            }
        };

        Ok(PatchSet {
            files: file_patches,
            format,
            generator,
        })
    }

    /// Parse diff text from a file.
    pub fn parse_file(&self, path: &Path) -> Result<PatchSet, RCompareError> {
        let content = std::fs::read_to_string(path)?;
        self.parse_string(&content)
    }

    /// Detect which tool generated the diff output.
    ///
    /// - "Index: " prefix → CVSDiff
    /// - "==== " prefix → Perforce
    /// - Otherwise → Diff (plain diff)
    pub fn detect_generator(lines: &[&str]) -> DiffGenerator {
        for line in lines {
            if line.starts_with("Index: ") {
                return DiffGenerator::CvsDiff;
            }
            if line.starts_with("==== ") {
                return DiffGenerator::Perforce;
            }
        }
        DiffGenerator::Diff
    }

    /// Detect the diff output format by scanning for characteristic patterns.
    pub fn detect_format(lines: &[&str]) -> DiffFormat {
        for line in lines {
            if PAT_UNIFIED.is_match(line) {
                return DiffFormat::Unified;
            }
            if PAT_CONTEXT.is_match(line) {
                return DiffFormat::Context;
            }
            if PAT_NORMAL.is_match(line) {
                return DiffFormat::Normal;
            }
            if PAT_RCS.is_match(line) {
                return DiffFormat::Rcs;
            }
            if PAT_ED.is_match(line) {
                return DiffFormat::Ed;
            }
        }
        DiffFormat::Unknown
    }

    /// Remove "\ No newline at end of file" markers and truncate the
    /// preceding line at its newline character.
    pub fn clean_no_newline(lines: &mut Vec<String>) {
        let mut i = 0;
        while i < lines.len() {
            if lines[i].starts_with("\\ No newline") {
                lines.remove(i);
                // Truncate the preceding line at its trailing newline
                if i > 0 {
                    if let Some(pos) = lines[i - 1].rfind('\n') {
                        lines[i - 1].truncate(pos);
                    }
                }
                // Don't increment i — the next line shifted down
            } else {
                i += 1;
            }
        }
    }

    /// Escape a path for diff output (add quotes if it contains spaces).
    pub fn escape_path(path: &str) -> String {
        if path.contains(' ') {
            format!("\"{}\"", path.replace('\\', "\\\\").replace('"', "\\\""))
        } else {
            path.to_string()
        }
    }

    /// Unescape a path from diff output (remove surrounding quotes and backslash escapes).
    pub fn unescape_path(path: &str) -> String {
        let trimmed = path.trim();
        if trimmed.starts_with('"') && trimmed.ends_with('"') && trimmed.len() >= 2 {
            let inner = &trimmed[1..trimmed.len() - 1];
            inner.replace("\\\"", "\"").replace("\\\\", "\\")
        } else {
            trimmed.to_string()
        }
    }
}

impl Default for PatchParser {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_generator_cvs() {
        let lines = vec!["Index: file.txt", "===", "--- file.txt"];
        assert_eq!(PatchParser::detect_generator(&lines), DiffGenerator::CvsDiff);
    }

    #[test]
    fn test_detect_generator_perforce() {
        let lines = vec!["==== //depot/file.txt#1 - file.txt ===="];
        assert_eq!(PatchParser::detect_generator(&lines), DiffGenerator::Perforce);
    }

    #[test]
    fn test_detect_generator_diff() {
        let lines = vec!["--- a/file.txt", "+++ b/file.txt"];
        assert_eq!(PatchParser::detect_generator(&lines), DiffGenerator::Diff);
    }

    #[test]
    fn test_detect_format_unified() {
        let lines = vec!["--- a/f", "+++ b/f", "@@ -1,3 +1,3 @@", " ctx"];
        assert_eq!(PatchParser::detect_format(&lines), DiffFormat::Unified);
    }

    #[test]
    fn test_detect_format_context() {
        let lines = vec!["*** a/f", "--- b/f", "***************"];
        assert_eq!(PatchParser::detect_format(&lines), DiffFormat::Context);
    }

    #[test]
    fn test_detect_format_normal() {
        let lines = vec!["1,3c4,6", "< old"];
        assert_eq!(PatchParser::detect_format(&lines), DiffFormat::Normal);
    }

    #[test]
    fn test_detect_format_rcs() {
        let lines = vec!["a3 2", "added line"];
        assert_eq!(PatchParser::detect_format(&lines), DiffFormat::Rcs);
    }

    #[test]
    fn test_detect_format_ed() {
        let lines = vec!["3,5c", "new text", "."];
        assert_eq!(PatchParser::detect_format(&lines), DiffFormat::Ed);
    }

    #[test]
    fn test_clean_no_newline() {
        let mut lines = vec![
            "-old line\n".to_string(),
            "\\ No newline at end of file".to_string(),
            "+new line\n".to_string(),
        ];
        PatchParser::clean_no_newline(&mut lines);
        assert_eq!(lines.len(), 2);
        assert_eq!(lines[0], "-old line");
    }

    #[test]
    fn test_escape_unescape_path() {
        assert_eq!(PatchParser::escape_path("simple.txt"), "simple.txt");
        assert_eq!(
            PatchParser::escape_path("path with spaces/file.txt"),
            "\"path with spaces/file.txt\""
        );
        assert_eq!(
            PatchParser::unescape_path("\"path with spaces/file.txt\""),
            "path with spaces/file.txt"
        );
        assert_eq!(PatchParser::unescape_path("simple.txt"), "simple.txt");
    }

    #[test]
    fn test_parse_string_unified() {
        let input = "\
--- a/file.txt\t2024-01-01
+++ b/file.txt\t2024-01-02
@@ -1,3 +1,3 @@
 line1
-old
+new
 line3";
        let parser = PatchParser::new();
        let result = parser.parse_string(input).unwrap();
        assert_eq!(result.format, DiffFormat::Unified);
        assert_eq!(result.generator, DiffGenerator::Diff);
        assert_eq!(result.files.len(), 1);
        assert_eq!(result.files[0].hunks.len(), 1);
    }

    #[test]
    fn test_parse_string_normal() {
        let input = "\
1c1
< old
---
> new";
        let parser = PatchParser::new();
        let result = parser.parse_string(input).unwrap();
        assert_eq!(result.format, DiffFormat::Normal);
        assert_eq!(result.files.len(), 1);
    }

    #[test]
    fn test_parse_empty() {
        let parser = PatchParser::new();
        let result = parser.parse_string("").unwrap();
        assert!(result.files.is_empty());
    }
}
