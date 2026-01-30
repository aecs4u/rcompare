use rcompare_common::{
    DifferenceType, FilePatch, Hunk, PatchDifference, RCompareError,
};
use regex::Regex;
use std::sync::LazyLock;

// RCS add command: aN M — add M lines after line N
static RCS_ADD: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^a(\d+)\s+(\d+)$").unwrap()
});

// RCS delete command: dN M — delete M lines starting at line N
static RCS_DELETE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^d(\d+)\s+(\d+)$").unwrap()
});

/// Parse RCS diff format into a list of FilePatches.
///
/// RCS format uses two commands:
/// - `aN M` — add M lines after line N (followed by M content lines)
/// - `dN M` — delete M lines starting at line N (no content lines follow)
pub fn parse_rcs(lines: &[&str]) -> Result<Vec<FilePatch>, RCompareError> {
    let mut fp = FilePatch::new();
    let mut i = 0;

    while i < lines.len() {
        if let Some(cap) = RCS_ADD.captures(lines[i]) {
            let after_line: usize = cap[1].parse().unwrap_or(0);
            let count: usize = cap[2].parse().unwrap_or(0);

            i += 1;

            let mut diff = PatchDifference::new(
                DifferenceType::Insert,
                after_line,
                after_line + 1,
            );
            for _ in 0..count {
                if i < lines.len() {
                    diff.dest_lines.push(format!("{}\n", lines[i]));
                    i += 1;
                }
            }

            let mut hunk = Hunk::new(after_line, after_line + 1);
            hunk.source_count = 0;
            hunk.dest_count = count;
            hunk.differences.push(diff);
            fp.hunks.push(hunk);
        } else if let Some(cap) = RCS_DELETE.captures(lines[i]) {
            let start_line: usize = cap[1].parse().unwrap_or(0);
            let count: usize = cap[2].parse().unwrap_or(0);

            i += 1;

            let mut diff =
                PatchDifference::new(DifferenceType::Delete, start_line, start_line);
            // RCS delete has no content lines — we add empty placeholders
            for _ in 0..count {
                diff.source_lines.push(String::new());
            }

            let mut hunk = Hunk::new(start_line, start_line);
            hunk.source_count = count;
            hunk.dest_count = 0;
            hunk.differences.push(diff);
            fp.hunks.push(hunk);
        } else {
            i += 1;
        }
    }

    if fp.hunks.is_empty() {
        Ok(Vec::new())
    } else {
        Ok(vec![fp])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_rcs_add() {
        let input = "\
a3 2
added line 1
added line 2";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_rcs(&lines).unwrap();
        assert_eq!(result.len(), 1);
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Insert);
        assert_eq!(hunk.differences[0].dest_lines.len(), 2);
        assert_eq!(hunk.dest_count, 2);
    }

    #[test]
    fn test_parse_rcs_delete() {
        let input = "\
d5 3";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_rcs(&lines).unwrap();
        assert_eq!(result.len(), 1);
        let hunk = &result[0].hunks[0];
        assert_eq!(hunk.differences[0].diff_type, DifferenceType::Delete);
        assert_eq!(hunk.source_count, 3);
    }

    #[test]
    fn test_parse_rcs_multiple_commands() {
        let input = "\
d1 2
a5 1
new line";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_rcs(&lines).unwrap();
        assert_eq!(result[0].hunks.len(), 2);
        assert_eq!(result[0].hunks[0].differences[0].diff_type, DifferenceType::Delete);
        assert_eq!(result[0].hunks[1].differences[0].diff_type, DifferenceType::Insert);
    }

    #[test]
    fn test_parse_rcs_empty() {
        let input = "";
        let lines: Vec<&str> = input.lines().collect();
        let result = parse_rcs(&lines).unwrap();
        assert!(result.is_empty());
    }
}
